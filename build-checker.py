import os
import sys
import glob
import re

from pprint import pprint

BUILD_CONFIGURATION_PATH = r"programming/bigworld_client/build/cmake"


def find_configuration_cmakes(path_root):
    glob_spec = os.path.join(path_root, BUILD_CONFIGURATION_PATH, "BWConfiguration_*.cmake")
    def _stripName( n ):
        return os.path.basename(n.replace( '\\', '/' ).replace( 'cmake/BWConfiguration_', '' ).replace( '.cmake', '' ))
    return dict([ (_stripName(x), os.path.normpath(x)) for x in glob.glob(glob_spec) ])


def parse_cmake_config(filename):
    content = open(filename).read()

    def _process_raw_lib_block(content):
        def _strip_line(l):
            if '#' in l:
                l = l[:l.index('#')]
            m = re.match( r'([\\\./\w]+)?\s*([\\\./\w]+)', l.strip() ) # blah      stuff
            if m is not None:
                return m.group(1), m.group(2)
        return [ _strip_line(x) for x in content.split("\n") if _strip_line(x) ]

    libs = []
    
    m = re.findall( r"BW_LIBRARY_PROJECTS(.*?)\)", content, re.DOTALL|re.MULTILINE )
    for group in m:
        libs = libs + _process_raw_lib_block(group)

    m = re.findall( r"BW_BINARY_PROJECTS(.*?)\)", content, re.DOTALL|re.MULTILINE )
    for group in m:
        libs = libs + _process_raw_lib_block(group)
    
    pprint(libs)


if __name__ == "__main__":
    configs = find_configuration_cmakes(sys.argv[1])
    libs = parse_cmake_config(configs.items()[2][1])