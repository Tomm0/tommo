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
from os.path import join, normpath, relpath
from subprocess import CalledProcessError

from svn_shelve_config import CONFIG

START_ID = 1000
DEBUG = False

def call_svn( *args ):
    try:
        return subprocess.check_output( ["svn"] + list(args) )
    except CalledProcessError as e:
        # stderr gets directed out to user already, just exit with code.
        sys.exit(e.returncode)
    except KeyboardInterrupt as e:
        sys.exit(1)


def print_info( *args ):
    print " ".join(str(x) for x in args)

def print_debug( *args ):
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
    assuming file system guarantees mutual exclusivity. Only danger is a client
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
                print_debug("Last id =", last_id)
            except ValueError:
                print_debug("%s contains invalid content (%s). Assuming first use." % (id_file, content))
                last_id = START_ID
            except IOError:
                print_debug("Could not read content from %s. Assuming first use." % (id_file,))

            # Generate new ID
            new_id = last_id + 1

            # Write out newly generated ID
            fp.seek(0)
            fp.truncate()
            fp.write(str(new_id))
    except EnvironmentError as e:
        fatal("Could not open and exclusively lock %s" % (id_file,))

    print_debug("Generated id =", new_id)
    return new_id

def get_storage_path(id):
    return join(CONFIG.local_storage, str(id))


def check_environment():
    try:
        result = call_svn("--version")
    except WindowsError:
        fatal("Subversion not found on system path")
    
def humanize_key(s):
    return s.replace("_", " ").title()

def humanize_value(v):
    if type(v) is list:
        return ", ".join([humanize_value(x) for x in v])
    else:
        return str(v)

def do_shelve(target_dir, message):
    print_debug("Shelving", target_dir, message)

    # Get information about SVN repo
    info = call_svn("info", target_dir)
    info = dict([ tuple(x.split(': ')) for x in info.strip().splitlines()])

    # Generate patch file based on target
    diff = call_svn("diff", target_dir)
    if not diff:
        print "Nothing to shelve"
        return
    
    modifiedPaths = re.findall("Index: (.*)", diff)
    modifiedPaths = [ normpath(x.strip()) for x in modifiedPaths ]
    modifiedPaths = [ relpath(x, target_dir) for x in modifiedPaths ]

    for path in modifiedPaths:
        print_info("M\t", path) # TODO: get correct status code
    print_info("")

    # Generate new shelve location
    new_id = generate_new_id()
    storage_path = get_storage_path(new_id)

    while os.path.isdir( storage_path ):
        new_id = generate_new_id()
        storage_path = get_storage_path(new_id)
    os.makedirs(storage_path)

    # Generate meta information based on target
    meta = {
        "id": new_id,
        "target_dir": target_dir,
        "local_timestamp": time.ctime(time.time()),
        "url": info["URL"],
        "revision": int(info["Revision"]),
        "hostname": socket.gethostname(),
        "username": getpass.getuser(),
        "modified": modifiedPaths,
        "message": message
    }
    
    # Write all
    meta_filename = join(storage_path, "meta")
    patch_filename = join(storage_path, "patch")
    
    file(meta_filename, "wb").write(pickle.dumps(meta))
    print_debug("Wrote", meta_filename)
    
    file(patch_filename, "wb").write(diff)
    print_debug("Wrote", patch_filename)

    print_info("Shelved changelist:", new_id)




def do_unshelve(shelve_id, target_dir):
    print_debug("Unshelving", shelve_id, target_dir)
    storage_path = get_storage_path(shelve_id)

    meta_filename = join(storage_path, "meta")
    patch_filename = join(storage_path, "patch")

    try:
        meta = pickle.loads(open(meta_filename, "rb").read())
        patch = open(patch_filename, "rb").read()
    except IOError:
        fatal("%d is not a valid id")

    # Apply patch against target directory
    # TODO: see if we can suggest a better match
    print call_svn("patch", patch_filename, target_dir)


def do_info(shelve_id):
    print_debug( "Fetching info", shelve_id )
    storage_path = get_storage_path(shelve_id)

    meta_filename = join(storage_path, "meta")
    patch_filename = join(storage_path, "patch")

    try:
        meta = pickle.loads(open(meta_filename, "rb").read())
        patch = open(patch_filename, "rb").read()
    except IOError:
        fatal("%d is not a valid id")

    for key, value in meta.iteritems():
        print_info("%s : %s" % (humanize_key(key), humanize_value(value)))
    
    
def _mp_test_proc(procidx):
    global DEBUG
    DEBUG = False # Don't spam the subprocess output while testing
    new_id = generate_new_id()
    return new_id

def do_tests():
    print_info("Testing single ID generation: new_id = %d" % generate_new_id())
    
    gen_max = 10000
    num_procs = 32
    print_info("Testing concurrent distributed ID generation...")
    
    pool = multiprocessing.Pool(processes=num_procs)
    mproc_results = [pool.apply_async(_mp_test_proc, (x,)) for x in xrange(gen_max)]
    all_ids = [p.get() for p in mproc_results]
    is_unique = len(all_ids) == len(set(all_ids))

    if is_unique:
        print_info("...successfully generated %d unique ID's across %d processes." % (gen_max, num_procs))
    else:
        fatal("Non-unique ID's generated.")



def main():
    check_environment()

    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-s", "--shelve", action="store_true")
    group.add_argument("-u", "--unshelve", metavar="ID", default=0, type=int)
    group.add_argument("-i", "--info", metavar="ID", default=0, type=int)
    group.add_argument("-t", "--test", action="store_true")
    parser.add_argument("-d", "--debug", action="store_true")
    parser.add_argument("-m", "--message", metavar="MESSAGE", default="", type=str)
    parser.add_argument("target_dir", nargs="?", default=os.getcwd(), help="Directory on which to operate (cwd by default).")
    args = parser.parse_args()

    global DEBUG
    DEBUG = args.debug

    if not os.path.isabs(args.target_dir):
        args.target_dir = normpath(join(os.getcwd(), args.target_dir))

    if args.test:
        do_tests()
    if args.shelve:
        do_shelve(args.target_dir, args.message)
    elif args.unshelve:
        do_unshelve(args.unshelve, args.target_dir)
    elif args.info:
        do_info(args.info)


if __name__ == "__main__":
    main()
