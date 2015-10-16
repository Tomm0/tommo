import os
import sys
import pickle
import subprocess

from pprint import pprint
from os.path import join, normpath

from svn_shelve_config import CONFIG

DEBUG = False

def trace( *args ):
	if DEBUG:
		print "(DEBUG)", " ".join( [str(x) for x in args] )

def getExistingShelve( id ):
	storageLocation = join( CONFIG.local_storage, str(id) )
	if os.path.isdir( storageLocation ):
		return storageLocation
	else:
		return None



def main():
	id = int(sys.argv[1])
	storageLocation = getExistingShelve( id )
	if not storageLocation:
		print "ERROR: %s is not a valid shelve ID" % id
		return

	trace( "Found shelve %s at %s" % (id, storageLocation) )
	metaFilename = join(storageLocation, "meta")
	patchFilename = join(storageLocation, "patch")

	meta = pickle.loads( open( metaFilename, "rb" ).read() )
	trace( "Read", metaFilename )

	patch = open( patchFilename, "rb" ).read()
	trace( "Read", patchFilename )

	# Just print info and quit?
	if "-info" in sys.argv:
		print "ID: %s" % meta["id"]
		print "Owner: %s@%s" % (meta["username"], meta["hostname"])
		print "Created: %s" % meta["local_timestamp"]
		print "URL: %s" % meta["url"]
		print "Message: %s" % meta["message"]
		print
		for filename in meta["modified"]:
			print "M\t%s" % filename
		return

	# Check that our target folder matches where it was shelved from (by URL)
	# If it doesn't match, ask the user if they really want to try patching anyway


	# Apply patch
	cmd = [ CONFIG.patch_bin, "-s", "--binary", "-i", patchFilename ]
	trace( "cmd", cmd )
	subprocess.call( cmd )


if __name__ == "__main__":
	main()