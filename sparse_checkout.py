import sys
import os
import subprocess
import argparse
import getpass
import pysvn


def ssl_server_trust_prompt(trust_dict):
    return True, trust_dict['failures'], True


def get_login(realm, username, may_save):
    username = raw_input("Username: ")
    password = getpass.getpass()
    return True, username, password, True


def svn(*args):
    full_args = " ".join(args)
    full_cmd = "svn " + full_args
    #print ">", full_cmd
    os.system(full_cmd)


def parse_conf_file(filename):
    def _strip_line(l):
        if '#' in l:
            l = l[l.index('#'):]
        return l.strip()

    inclusions = []
    exclusions = []

    for line in [ _strip_line(x) for x in open(filename, "r").readlines() ]:
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
    

def do_sparse_checkout(url, dest, exclusions, inclusions):
    svn_client = pysvn.Client()
    svn_client.callback_ssl_server_trust_prompt = ssl_server_trust_prompt
    svn_client.callback_get_login = get_login
    svn_client.set_interactive(True)

    # Exclusions/inclusions must start with a /. 
    filtered_exclusions = [ '/' + x for x in exclusions ]
    filtered_inclusions = [ '/' + x for x in inclusions ]

    svn_up_empty = []
    svn_up_infinite = []

    print "Preparing..."

    # 0. Determine revision we are updating to
    svn_info = svn_client.info2(url, recurse=False)
    target_revision = svn_info[0][1].rev

    # 1. Iterate up through the exclusion paths, checking out only empty.
    # Treat inclusions as exclusions at this point for convenience, as we
    # will need to make sure we have all the intermediate nodes available,
    # and we will do a proper update on inclusion leaf node later
    seen_exclusions = set()
    for path in filtered_exclusions + filtered_inclusions:
        full_path = ''
        for path_part in path.split('/'):
            full_path = full_path + '/' + path_part if path_part != '' else ''
            if full_path in seen_exclusions:
                continue

            svn_up_empty.append(dest + full_path)
            seen_exclusions.add(full_path)

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
                if full_path in seen_exclusions or full_path in seen_checkouts:
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
    svn_client.checkout(url, dest, recurse=False)
    for path in svn_up_empty:
        svn_client.update(path, depth=pysvn.depth.empty, revision=target_revision )

    # 5. Do actual non-sparse content updates
    print "Updating..."
    for path in svn_up_infinite:
        svn('up', '--depth=infinity', '--revision', str(target_revision.number), path)



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Sparse SVN checkout')
    parser.add_argument('url', type=str, help='Source URL to checkout from.')
    parser.add_argument('path', type=str, help='Target path to checkout into.')
    parser.add_argument('-p', '--profile', default='', type=str, help='Sparse configuration profile.')

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
        do_sparse_checkout(args.url, args.path, exclusions, inclusions)
    except pysvn.ClientError as e:
        print e.message
        sys.exit(1)

