"""Functions for gathering Dewbee components on the canvas and syncing them
with their installed user object versions.

The logic mirrors ``ladybug_rhino.versioning.gather`` and
``ladybug_rhino.versioning.diff`` but is simplified for Dewbee, which ships
as a single plugin with a flat user-object folder layout
(``<GH UserObjects>/dewbee/*.ghuser``).
"""
import os

try:
    import System.Drawing
except ImportError:
    raise ImportError("Failed to import System.")

try:
    import Grasshopper.Kernel as gh
    from Grasshopper.Folders import UserObjectFolders
except ImportError:
    raise ImportError("Failed to import Grasshopper.")

try:
    from ladybug_rhino.grasshopper import give_warning
except ImportError:  # pragma: no cover - optional dependency in non-GH runs
    def give_warning(component, message):
        try:
            from Grasshopper.Kernel import GH_RuntimeMessageLevel as _msg
            component.AddRuntimeMessage(_msg.Warning, str(message))
        except Exception:
            print('WARNING: {}'.format(message))


# Name prefix and Grasshopper category used to identify Dewbee components
DEWBEE_NAME_PREFIX = 'DB'
DEWBEE_CATEGORY = 'Dewbee'

# Target sub-folder inside the Grasshopper UserObjects directory where
# Dewbee .ghuser files are installed (kept in sync with the installer).
GHUSER_TARGET_FOLDER_NAME = 'dewbee'


def _uo_folder():
    """Get the root Dewbee user-object folder on disk."""
    if not UserObjectFolders or len(UserObjectFolders) == 0:
        raise IOError("Could not find Grasshopper UserObjects directory.")
    return os.path.join(UserObjectFolders[0], GHUSER_TARGET_FOLDER_NAME)


def is_dewbee(component):
    """Check if a component is a part of Dewbee.

    A component is considered Dewbee if its Name starts with the ``DB``
    prefix or if its Category is ``Dewbee``.
    """
    try:
        name = str(component.Name)
    except Exception:
        return False
    if name.split(' ')[0] == DEWBEE_NAME_PREFIX:
        return True
    try:
        return str(component.Category) == DEWBEE_CATEGORY
    except Exception:
        return False


def gather_canvas_components(component):
    """Get all of the Dewbee components on the same canvas as the input component.

    This will also gather any Dewbee components inside of clusters.

    Args:
        component: A Grasshopper component object. Typically, this should
            be the exporter/updater component object, which can be accessed
            through the ``ghenv.Component`` call.

    Returns:
        A tuple of Dewbee component objects on the same canvas as the
        input component. The input component itself is excluded from the
        result.
    """
    components = []
    document = component.OnPingDocument()
    for comp_obj in document.Objects:
        if type(comp_obj) == type(component):  # GHPython component
            if is_dewbee(comp_obj):
                components.append(comp_obj)
        elif type(comp_obj) == gh.Special.GH_Cluster:
            cluster_doc = comp_obj.Document("")
            if not cluster_doc:
                continue
            for cluster_obj in cluster_doc.Objects:
                if type(cluster_obj) == type(component) and \
                        is_dewbee(cluster_obj):
                    if cluster_obj.Locked:
                        continue
                    components.append(cluster_obj)

    # remove the exporter component itself from the array
    components = tuple(
        comp for comp in components
        if comp.InstanceGuid != component.InstanceGuid
    )
    return components


def has_version_changed(user_object, component):
    """Check if the version (Message) of a component differs from a user object."""
    return not user_object.Message == component.Message


def update_port(p1, p2):
    """Update one port based on another. Returns True if the port changed."""
    if hasattr(p1, 'TypeHint'):  # input
        if p1.Name != p2.Name:
            p2.NickName = p1.NickName
            p2.Name = p1.Name
        if p1.TypeHint.TypeName != p2.TypeHint.TypeName:
            p2.TypeHint = p1.TypeHint
        if str(p1.Access) != str(p2.Access):
            p2.Access = p1.Access
        return True
    else:  # output
        if p1.Name != p2.Name:
            p2.NickName = p1.NickName
            p2.Name = p1.Name
        return True


def update_ports(c1, c2):
    """Update all of the ports of one component based on another.

    Returns True if the input/output signatures differ.
    """
    for i in range(c1.Params.Input.Count):
        if not update_port(c1.Params.Input[i], c2.Params.Input[i]):
            return True
    for i in range(c1.Params.Output.Count):
        if not update_port(c1.Params.Output[i], c2.Params.Output[i]):
            return True
    return False


def input_output_changed(user_object, component):
    """Check if any of the inputs or outputs have changed between two components."""
    if user_object.Params.Input.Count != component.Params.Input.Count:
        return True
    elif user_object.Params.Output.Count != component.Params.Output.Count:
        return True
    return update_ports(user_object, component)


def insert_new_user_object(user_object, component, doc):
    """Insert a new user object next to an existing component in the document."""
    x = component.Attributes.Pivot.X + 30
    y = component.Attributes.Pivot.Y - 20
    user_object.Attributes.Pivot = System.Drawing.PointF(x, y)
    doc.AddObject(user_object, False, 0)


def mark_component(doc, component, note=None):
    """Put a circular red group around a component and label it with a note."""
    note = note or 'There is a change in the input or output! ' \
        'Replace this component manually.'
    grp = gh.Special.GH_Group()
    grp.CreateAttributes()
    grp.Border = gh.Special.GH_GroupBorder.Blob
    grp.AddObject(component.InstanceGuid)
    grp.Colour = System.Drawing.Color.IndianRed
    grp.NickName = note
    doc.AddObject(grp, False)
    return True


def sync_component(component, syncing_component):
    """Sync a Dewbee component on the canvas with its installed user object version.

    This identifies the component by name in the Dewbee user-object folder,
    injects the code from that user object into the component, and (if the
    component inputs or outputs have changed) circles the component in red
    and drops the new user object next to the outdated component.

    Args:
        component: A Grasshopper component object on the canvas to be synced.
        syncing_component: An object for the component that is doing the
            syncing. This is used to give warnings and access the Grasshopper
            document. Typically, this can be accessed through the
            ``ghenv.Component`` call.

    Returns:
        ``False`` if there was nothing to update, otherwise a string message
        describing the update result.
    """
    # locate the user object file on disk
    ghuser_file = '%s.ghuser' % component.Name
    fp = os.path.join(_uo_folder(), ghuser_file)

    if not os.path.isfile(fp):
        warning = 'Failed to find the userobject for %s' % component.Name
        give_warning(syncing_component, warning)
        return False

    # load the instance of the user object from the file
    uo = gh.GH_UserObject(fp).InstantiateObject()

    # check to see if the version of the userobject has changed
    if not has_version_changed(uo, component):
        return False

    # the version has changed; update the code
    component.Code = uo.Code
    doc = syncing_component.OnPingDocument()

    # schedule a re-solve for the updated component
    def call_back(document):
        component.ExpireSolution(False)

    doc.ScheduleSolution(2, gh.GH_Document.GH_ScheduleDelegate(call_back))

    # if inputs or outputs have changed, drop the new user object and mark
    if input_output_changed(uo, component):
        insert_new_user_object(uo, component, doc)
        mark_component(doc, component)
        return 'Cannot update %s. Replace manually.' % component.Name

    return 'Updated %s' % component.Name
