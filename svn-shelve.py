"""
    svn-shelve --shelve --revert .
    svn-shelve --unshelve 1234 .
    svn-shelve --info 1234
"""
import os
import re
import sys
import argparse
import pickle
import time
import socket
import getpass
import subprocess
import portalocker
import multiprocessing

from pprint import pprint
from os.path import join, normpath
from subprocess import CalledProcessError

from svn_shelve_config import CONFIG

START_ID = 1000
DEBUG = True

def call_svn( *args ):
    return subprocess.check_output( ["svn"] + list(args) )


def message( *args ):
    print " ".join(str(x) for x in args)

def debug( *args ):
    if DEBUG:
        print "(DEBUG)", " ".join( [str(x) for x in args] )

def fatal( *args ):
    print "ERROR:", " ".join(str(x) for x in args)
    sys.exit(1)

def generate_new_id():
    """
    Generates a new unique ID by using a centralized id file, which we gain
    an exclusive lock on so that only one client may be generating an ID at 
    a particular time. This should guarantee unique id's in a distributed fashion,
    assuming file system guarantees mutual exclusivity. Only ddanger is a client
    may hang up and leave the file locked, however this should be unlikely.
    """
    # Check location exists
    if not os.path.isdir(CONFIG.local_storage):
        fatal("Configured path not found at", CONFIG.local_storage)

    id_file = join(CONFIG.local_storage, ".id_gen")

    # Open file and gain lock
    try:
        with open(id_file, "a+") as fp:
            portalocker.lock(fp, portalocker.LOCK_EX)

            # Read last ID generated
            fp.seek(0)
            try:
                content = fp.read().strip()
                last_id = int(content)
                debug("Last id =", last_id)
            except ValueError:
                debug("%s contains invalid content (%s). Assuming first use." % (id_file, content))
                last_id = START_ID
            except IOError:
                debug("Could not read content from %s. Assuming first use." % (id_file,))

            # Generate new ID
            new_id = last_id + 1

            # Write out newly generated ID
            fp.seek(0)
            fp.truncate()
            fp.write(str(new_id))
    except EnvironmentError as e:
        fatal("Could not open and exclusively lock %s" % (id_file,))

    debug("Generated id", new_id)
    return new_id




def check_environment():
    try:
        result = call_svn( ["--version"] )
    except WindowsError:
        print "ERROR: Subversion not found on system path"
        sys.exit(1)
    


def do_shelve( targetDir ):
    debug( "Shelving", targetDir )


def do_unshelve( shelveID, targetDir ):
    debug( "Unshelving", shelveID, targetDir)


def do_info( shelveID ):
    debug( "Fetching info", shelveID )
    
    
def _mp_test_proc(procidx):
    global DEBUG
    DEBUG = False # Don't spam the subprocess output while testing
    new_id = generate_new_id()
    return new_id

def do_tests():
    message("Testing single ID generation: new_id = %d" % generate_new_id())
    
    gen_max = 10000
    num_procs = 32
    message("Testing concurrent distributed ID generation...")
    
    pool = multiprocessing.Pool(processes=num_procs)    
    pool = multiprocessing.Pool(processes=4)
    mproc_results = [pool.apply_async(_mp_test_proc, (x,)) for x in xrange(gen_max)]
    all_ids = [p.get() for p in mproc_results]
    is_unique = len(all_ids) == len(set(all_ids))

    if is_unique:
        message("...successfully generated %d unique ID's across %d processes." % (gen_max, num_procs))
    else:
        fatal("Non-unique ID's generated.")



def main():
    check_environment()

    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument( "-s", "--shelve", action="store_true" )
    group.add_argument( "-u", "--unshelve", metavar="ID", default=0, type=int )
    group.add_argument( "-i", "--info", metavar="ID", default=0, type=int )
    group.add_argument( "-t", "--test", action="store_true" )
    parser.add_argument( "target_dir", nargs="?", default=os.getcwd(), help="Directory on which to operate (cwd by default)." )
    args = parser.parse_args()

    if args.test:
        do_tests()
    if args.shelve:
        do_shelve( args.target_dir )
    elif args.unshelve:
        do_unshelve( args.unshelve, args.target_dir )
    elif args.info:
        do_info( args.info )

    return

    cwd = os.getcwd()
    cwd = cwd[0].upper() + cwd[1:]
    cwd = cwd.replace( "\\", "/")
    trace( "cwd", cwd )

    svn = pysvn.Client()
    info = svn.info( cwd )

    diffContent = svn.diff( tmp_path = ".",
        url_or_path = cwd,
        relative_to_dir = cwd )

    # TODO: adds and deletes are all just going to appear as "M" here...
    # Probably better to use a proper svn status operation.
    modifiedPaths = re.findall( "Index: (.*)", diffContent )
    modifiedPaths = [ x.strip() for x in modifiedPaths ]
    #trace( "modifiedPaths", modifiedPaths)

    if len(modifiedPaths) == 0:
        print "Nothing to shelve"
        return

    for changed in modifiedPaths:
        print "M\t%s" % changed
    print
    
    newID, storageLocation = getNewShelve()
    meta = {
        "id": newID,
        "cwd": cwd,
        "local_timestamp": time.ctime(time.time()),
        "url": info["url"],
        "revision": info["revision"].number,
        "hostname": socket.gethostname(),
        "username": getpass.getuser(),
        "modified": modifiedPaths,
        "message": "todo"
    }

    metaFilename = join(storageLocation, "meta")
    patchFilename = join(storageLocation, "patch")
    
    file( metaFilename, "wb" ).write( pickle.dumps(meta) )
    trace( "Wrote", metaFilename )
    
    file( patchFilename, "wb" ).write( diffContent )
    trace( "Wrote", patchFilename )

    print "Shelved changelist:", newID

    # Revert, if requested
    shouldRevert = "-revert" in sys.argv
    if shouldRevert:
        svn.revert( cwd, recurse = True )
        print "Reverted local copy"



if __name__ == "__main__":
    main()
    
