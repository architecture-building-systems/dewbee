"""
Sync the Dewbee components in a Grasshopper file with the version of the
components that currently exist in the Grasshopper toolbar.
-
This is useful for updating old Grasshopper definitions to newer Dewbee
plugin versions. However, this component will sync components regardless of
version number or date, even if the components in the toolbar are of an
older version than those currently on the Grasshopper canvas.
-
Any components that cannot be updated automatically (because their inputs or
outputs have changed) will be circled in red and should be replaced manually.
-

    Args:
        _sync: Set to "True" to have this component to search through the
            current Grasshopper file and sync all Dewbee components
            with the version in the Grasshopper toolbar.

    Returns:
        report: Errors, warnings, etc.
"""

ghenv.Component.Name = 'DB Sync Grasshopper File'
ghenv.Component.NickName = 'DBSyncGHFile'
ghenv.Component.Message = '0.1.0'
ghenv.Component.Category = 'Dewbee'
ghenv.Component.SubCategory = '0 :: Miscellaneous'
ghenv.Component.AdditionalHelpFromDocStrings = '1'

try:
    ghenv.Component.ToggleObsolete(False)
except Exception:
    pass

try:
    from dewbee.versioning import gather_canvas_components, sync_component
except ImportError as e:
    raise ImportError('\nFailed to import dewbee:\n\t{}'.format(e))

try:
    from ladybug_rhino.grasshopper import all_required_inputs, give_warning
except ImportError as e:
    raise ImportError('\nFailed to import ladybug_rhino:\n\t{}'.format(e))


if all_required_inputs(ghenv.Component) and _sync:
    # load all of the GHPython userobjects and update the versions
    components = gather_canvas_components(ghenv.Component)
    report_init = []
    for comp in components:
        try:
            report_init.append(sync_component(comp, ghenv.Component))
        except Exception:
            if hasattr(comp, 'Name'):
                msg = 'Failed to Update "{}"'.format(comp.Name)
                print(msg)
                give_warning(ghenv.Component, msg)
    report = '\n'.join(r for r in report_init if r)
