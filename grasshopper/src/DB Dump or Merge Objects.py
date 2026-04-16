"""
Dump any honeybee object to a JSON file. You can use "HB Load Objects" component
to load the objects from the file back into Grasshopper.
-
This version adds merge behavior for object-library JSON files:
If the target file does not exist, it is created.
If the target file exists and contains a JSON object/dictionary, objects with
matching identifiers are replaced and new ones are appended.
If a single Honeybee Model is written, the file is overwritten as usual.
-

    Args:
        _hb_objs: A list of Honeybee objects to be written to a file.
        _name_: A name for the file to which the honeybee objects will be written.
            (Default: 'unnamed').
        _folder_: An optional directory into which the honeybee objects will be
            written. The default is set to the default simulation folder.
        indent_: An optional positive integer to set the indentation used in the
            resulting JSON file.
        abridged_: Set to "True" to serialize the object in its abridged form.
        _dump: Set to "True" to save the honeybee objects to file.
    
    Returns:
        report: Errors, warnings, and info about added/replaced objects.
        hb_file: The location of the file where the honeybee JSON is saved.
"""

ghenv.Component.Name = 'DB Dump or Merge Objects'
ghenv.Component.NickName = 'DumpMergeObjects'
ghenv.Component.Message = '0.0.1'
ghenv.Component.Category = 'Dewbee'
ghenv.Component.SubCategory = '0 :: Miscellaneous'

import os
import sys
import json
import codecs

try:  # import the core honeybee dependencies
    from honeybee.model import Model
    from honeybee.room import Room
    from honeybee.face import Face
    from honeybee.aperture import Aperture
    from honeybee.door import Door
    from honeybee.shade import Shade
    from honeybee.config import folders
except ImportError as e:
    raise ImportError('\nFailed to import honeybee:\n\t{}'.format(e))

try:  # import the core ladybug_rhino dependencies
    from ladybug_rhino.grasshopper import all_required_inputs, give_warning
except ImportError as e:
    raise ImportError('\nFailed to import ladybug_rhino:\n\t{}'.format(e))


def geo_object_warning(obj):
    """Give a warning that individual geometry objects should be added to a Model."""
    msg = 'An individual {} has been connected to the _hb_objs.\n' \
        'The recommended practice is to add this object to a Model and\n' \
        'serialize the Model instead of serializing individual objects.'.format(
            obj.__class__.__name__)
    print(msg)
    give_warning(ghenv.Component, msg)


def obj_to_dict(obj, abridged=False):
    """Serialize a Honeybee object to a dictionary."""
    try:
        return obj.to_dict(abridged=abridged)
    except TypeError:
        return obj.to_dict()


def open_utf8_read(path):
    """Open a UTF-8 file for reading in IronPython/Python 2."""
    return codecs.open(path, 'r', 'utf-8')


def open_utf8_write(path):
    """Open a UTF-8 file for writing in IronPython/Python 2."""
    return codecs.open(path, 'w', 'utf-8')


def load_existing_library(path):
    """Load an existing JSON library file.

    Returns:
        {} if file does not exist.
        Existing dictionary if valid.

    Raises:
        ValueError if the existing file is not a dictionary-based object library.
    """
    if not os.path.isfile(path):
        return {}

    with open_utf8_read(path) as fp:
        data = json.load(fp)

    if not isinstance(data, dict):
        raise ValueError(
            'Existing JSON file is not a dictionary-based object library.\n'
            'Merge is only supported for JSON files storing objects keyed by identifier.'
        )

    return data


def write_json(path, data, indent):
    """Write JSON to file as UTF-8."""
    with open_utf8_write(path) as fp:
        json.dump(data, fp, indent=indent, ensure_ascii=False)


if all_required_inputs(ghenv.Component) and _dump:
    report_msgs = []

    # set defaults
    name = _name_ if _name_ is not None else 'unnamed'
    folder = _folder_ if _folder_ is not None else folders.default_simulation_folder
    abridged = bool(abridged_)
    indent = indent_ if indent_ is not None else 4

    # choose file extension
    file_name = '{}.json'.format(name) if len(_hb_objs) > 1 or not \
        isinstance(_hb_objs[0], Model) else '{}.hbjson'.format(name)
    hb_file = os.path.join(folder, file_name)

    # warn about individual geometry objects
    geo_types = (Room, Face, Aperture, Door, Shade)
    for obj in _hb_objs:
        if isinstance(obj, geo_types):
            geo_object_warning(obj)

    # ensure output folder exists
    if not os.path.isdir(folder):
        os.makedirs(folder)

    # CASE 1: single Model -> overwrite as normal
    if len(_hb_objs) == 1 and isinstance(_hb_objs[0], Model):
        obj_dict = obj_to_dict(_hb_objs[0], abridged)
        write_json(hb_file, obj_dict, indent)
        report_msgs.append('Wrote single Model to file (overwrite mode).')

    # CASE 2: library/object dump -> merge by identifier
    else:
        # serialize incoming objects
        new_obj_dict = {}
        for obj in _hb_objs:
            try:
                obj_id = obj.identifier
            except AttributeError:
                raise ValueError(
                    'One of the connected objects does not have an "identifier" '
                    'attribute and cannot be stored in the library.'
                )
            new_obj_dict[obj_id] = obj_to_dict(obj, abridged)

        # load existing library, if any
        try:
            existing_obj_dict = load_existing_library(hb_file)
        except Exception as e:
            raise ValueError(
                'Failed to load existing JSON library file:\n{}\nPath: {}'.format(e, hb_file)
            )

        # determine added vs replaced BEFORE update
        added = []
        replaced = []
        for obj_id in new_obj_dict:
            if obj_id in existing_obj_dict:
                replaced.append(obj_id)
            else:
                added.append(obj_id)

        # merge
        existing_obj_dict.update(new_obj_dict)

        # write merged result
        write_json(hb_file, existing_obj_dict, indent)

        # report
        report_msgs.append('Merged objects into existing library.')
        report_msgs.append('Added: {}'.format(len(added)))
        report_msgs.append('Replaced: {}'.format(len(replaced)))

        if len(added) != 0:
            report_msgs.append('Added identifiers: {}'.format(', '.join(sorted(added))))
        if len(replaced) != 0:
            report_msgs.append('Replaced identifiers: {}'.format(', '.join(sorted(replaced))))

    report = '\n'.join(report_msgs)
    print(report)