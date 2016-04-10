import os
import sys
import glob
import re
import pysvn

from pprint import pprint

PROGRAMMING_BASE = r"programming"
LIB_BASE_PATH = r"programming/bigworld_client"
BUILD_CONFIGURATION_PATH = r"programming/bigworld_client/build/cmake"


def find_configuration_cmakes(path_root):
    glob_spec = os.path.join(path_root, BUILD_CONFIGURATION_PATH, "BWConfiguration_*.cmake")
    def _stripName( n ):
        return os.path.basename(n.replace( '\\', '/' ).replace( 'cmake/BWConfiguration_', '' ).replace( '.cmake', '' ))
    return dict([ (_stripName(x), os.path.normpath(x)) for x in glob.glob(glob_spec) ])


def parse_and_resolve_projects(filename, projects_base_path):
    content = open(filename).read()

    # Parse projects out of the cmake file
    def _process_raw_lib_block(content):
        def _strip_line(l):
            if '#' in l:
                l = l[:l.index('#')]
            m = re.match( r'([\\\./\w]+)?\s*([\\\./\w]+)', l.strip() ) # blah      stuff
            if m is not None:
                return m.group(1), m.group(2)
        return [ _strip_line(x) for x in content.split("\n") if _strip_line(x) ]

    projects = []
    
    m = re.findall( r"BW_LIBRARY_PROJECTS(.*?)\)", content, re.DOTALL|re.MULTILINE )
    for group in m:
        projects = projects + _process_raw_lib_block(group)

    m = re.findall( r"BW_BINARY_PROJECTS(.*?)\)", content, re.DOTALL|re.MULTILINE )
    for group in m:
        projects = projects + _process_raw_lib_block(group)

    # Resolve the projects to their absolute path
    def _resolve_path(relpath):
        return os.path.normpath( os.path.join(projects_base_path, relpath) )

    return [ (libname, _resolve_path(relpath)) for (libname, relpath) in projects ]


def get_modified_files(path):
    svn_client = pysvn.Client()
    try:
        changed_files = svn_client.diff_summarize(path)
    except pysvn.ClientError as e:
        print e.message
        sys.exit(1)
    return [ os.path.normpath( os.path.join( path, x.path ) ) for x in changed_files ]


def should_rebuild_configuration(config_projects, local_modifications):
    for project, project_path in config_projects:
        for modified_file in local_modifications:
            if modified_file.startswith(project_path):
                return True
    return False

if __name__ == "__main__":
    configs = find_configuration_cmakes(sys.argv[1])
    project_base = os.path.join( sys.argv[1], LIB_BASE_PATH )
    programming_base = os.path.join( sys.argv[1], PROGRAMMING_BASE )
    
    local_modifications = get_modified_files(programming_base)

    for config_name, config_path in configs.iteritems():
        projects = parse_and_resolve_projects(configs[config_name], project_base)
        if should_rebuild_configuration(projects, local_modifications):
            print "Rebuild", config_name


