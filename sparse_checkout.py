import sys
import os
import subprocess
import argparse
import getpass
import pysvn
import functools

_wcna = pysvn.wc_notify_action
INTERESTING_NOTIFICATIONS = [ 
    _wcna.add,
    _wcna.delete,
    _wcna.restore,
    _wcna.revert,
    _wcna.update_update,
    _wcna.update_add,
    _wcna.update_delete,
    _wcna.update_external ]

def ssl_server_trust_prompt(trust_dict):
    return True, trust_dict['failures'], True


def get_login(realm, username, may_save):
    username = raw_input("Username: ")
    password = getpass.getpass()
    return True, username, password, True


_SHOULD_CANCEL = False
def _kb_int_except_hook(type, value, traceback):
    global _SHOULD_CANCEL
    if type == KeyboardInterrupt:
        _SHOULD_CANCEL = True
    _original_except_hook(type, value, traceback)

_original_except_hook = sys.excepthook

sys.excepthook = _kb_int_except_hook

def svn_cancel_callback():
    return _SHOULD_CANCEL


def norm_drive_case(path):
    # Makes sure windows drive speifier is lower case for string comparisons
    if len(path) >= 2 and path[1] == ':':
        return path[0].lower() + path[1:]
    return path    


def svn_notification_callback(abs_base_path, event):
    if event['action'] in INTERESTING_NOTIFICATIONS:
        path = norm_drive_case(os.path.normpath(event['path']))
        abs_base_path = norm_drive_case(abs_base_path)
        if path.startswith(abs_base_path):
            path = path[len(abs_base_path)+1:].replace('\\', '/') 
        print "[%s] %s @ %d" % (str(event['action']).upper(), path, int(event['revision'].number))


def parse_conf_file(filename):
    def _strip_line(l):
        if '#' in l:
            l = l[:l.index('#')]
        return l.strip()

    absfilename = os.path.join( os.path.dirname( __file__ ), filename )

    inclusions = []
    exclusions = []

    for line in [ _strip_line(x) for x in open(absfilename, "r").readlines() ]:
        if len(line) == 0: continue

        if line.startswith('-'):
            exclusions.append(line[1:].strip())
        elif line.startswith('+'):
            inclusions.append(line[1:].strip())

    return exclusions, inclusions


_LS_CACHE = {}
def svn_ls(svn_client, url, revision):
    if url in _LS_CACHE:
        return _LS_CACHE[url]

    res = svn_client.ls(url, revision=revision)
    url_len = len(url) # name includes full url, remove this prefix
    dirs = [ x.name[url_len:] for x in res if x.kind == pysvn.node_kind.dir ]
    files = [ x.name[url_len:] for x in res if x.kind == pysvn.node_kind.file ]
    _LS_CACHE[url] = (dirs, files)
    return dirs, files


def pop_path(path):
    if not path:
        return path

    if path.endswith('/'):
        path = path[:-1]

    idx = path.rfind('/')
    if idx == -1:
        return ''

    return path[:idx+1] # Include trailing /


def is_dir_empty(path):
    return len(os.listdir(path)) == 0
    

def do_sparse_checkout(url, dest, exclusions, inclusions, dry_run, verbose):
    svn_client = pysvn.Client()
    svn_client.callback_ssl_server_trust_prompt = ssl_server_trust_prompt
    svn_client.callback_get_login = get_login
    svn_client.callback_cancel = svn_cancel_callback
    svn_client.set_interactive(True)

    if verbose:
        svn_client.callback_notify = functools.partial(svn_notification_callback, os.path.abspath(dest))

    # Exclusions/inclusions must start with a /. 
    filtered_exclusions = [ '/' + x for x in exclusions ]
    filtered_inclusions = [ '/' + x for x in inclusions ]

    svn_up_empty = []
    svn_up_infinite = []

    # 0. Determine revision we are updating to
    svn_info = svn_client.info2(url, recurse=False)
    target_revision = svn_info[0][1].rev

    # 1. Iterate up through the exclusion paths, checking out only empty.
    # Treat inclusions as exclusions at this point for convenience, as we
    # will need to make sure we have all the intermediate nodes available,
    # and we will do a proper update on inclusion leaf node later
    seen_exclusions = set()
    for path in filtered_inclusions + filtered_exclusions:
        full_path = ''
        is_inclusion = path in filtered_inclusions
        for path_part in path.split('/'):
            full_path = full_path + '/' + path_part if path_part != '' else ''
            if full_path in seen_exclusions:
                continue

            seen_exclusions.add(full_path)

            is_leaf_path = (full_path == path)
            full_dest_path = dest + full_path # full path on disk

            # Don't reclear intermediate paths if they don't already exist
            # (only need to update this folder on the first time through).
            if not os.path.exists(full_dest_path):
                svn_up_empty.append(full_dest_path)
            elif is_leaf_path and not is_dir_empty(full_dest_path) and not is_inclusion:
                svn_up_empty.append(full_dest_path) # Strip back existing                


    # 2. Iterate back down through the exclusion tree, doing an svn ls to
    # discover which paths we do actually want to checkout.
    seen_checkouts = set()
    for path in filtered_exclusions:
        path = pop_path(path) # Skip leaves which need to remain empty
        while path:
            full_url = url + path
            dirs, files = svn_ls(svn_client, full_url, target_revision)
            
            for subdir in (dirs + files):
                full_path = path + subdir
                full_dest_path = dest + full_path # full path on disk
                if full_path in seen_exclusions or full_path in seen_checkouts:
                    continue

                # If we already exist, then don't re-checkout. However if the folder is
                # empty, it may be a previous exclusion (which currently have empty folders),
                # so just in case, do an update at this location (TODO: maybe use sparse marker 
                # files to make this explicit?)
                if os.path.exists(full_dest_path) and not (os.path.isdir(full_dest_path) and is_dir_empty(full_dest_path)):
                    continue
                
                svn_up_infinite.append(dest + full_path)
                seen_checkouts.add(full_path)

            path = pop_path(path)

    # 3. Go through and update explicit inclusions. We can simply do a
    # SVN up on the inlcusion paths, since we have the leaf path updated
    # to empty during the exclusion step.
    for path in filtered_inclusions:
        svn_up_infinite.append(dest + path)


    # 4. Populate the sparse folders
    if not os.path.exists(dest):  # TODO: check is a valid svn WC
        if dry_run:
            print "svn co --non-recursive", url, dest
        else:
            svn_client.checkout(url, dest, recurse=False)

    for path in svn_up_empty:
        if dry_run:
            print "svn up --depth=empty", path
        else:
            svn_client.update(path, depth=pysvn.depth.empty, revision=target_revision )

    # 5. Do actual non-sparse content updates
    for path in svn_up_infinite:
        if dry_run:
            print "svn up --set-depth=infinity", path
        else:
            svn_client.update(path, depth=pysvn.depth.infinity, revision=target_revision )



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Sparse SVN checkout')
    parser.add_argument('url', type=str, help='Source URL to checkout from.')
    parser.add_argument('path', type=str, help='Target path to checkout into.')
    parser.add_argument('-p', '--profile', default='', type=str, help='Sparse configuration profile.')
    parser.add_argument('-d', '--dry-run', default=False, action="store_true", help="Display SVN actions that would take place without actually performing them.")
    parser.add_argument('-v', '--verbose', default=False, action="store_true", help="Display verbose information about operations performed.")

    args = parser.parse_args()

    if args.profile:
        if '.conf' not in args.profile:
            args.profile = args.profile + '.conf'
    else:
        print "ERROR: --profile not set"
        sys.exit(-1) ## TODO: support default action

    try:
        exclusions, inclusions = parse_conf_file(args.profile)
    except IOError:
        print 'ERROR: failed to parse %s' % (args.profile,)
        sys.exit(-1)

    try:
        do_sparse_checkout(args.url, args.path, exclusions, inclusions,
                           dry_run=args.dry_run, verbose=args.verbose)
    except pysvn.ClientError as e:
        print e.message
        sys.exit(1)
    except KeyboardInterrupt:
        _SHOULD_CANCEL = True
        sys.exit(1)


