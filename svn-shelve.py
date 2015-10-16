import os
import re
import sys
import pysvn
import argparse
import pickle
import time
import socket
import getpass

from pprint import pprint
from os.path import join, normpath

from svn_shelve_config import CONFIG

START_ID = 1000
DEBUG = False

def trace( *args ):
	if DEBUG:
		print "(DEBUG)", " ".join( [str(x) for x in args] )

def getNewShelve():
	# Find the next available ID slot on the storage
	# TODO: devise a distributed mechanism to determine a new
	# ID, without ever re-using an old ID, and guarantee every 
	# new ID unique (each client gain exclusive lock to .id file 
	# on server?)
	newID = START_ID
	while True:
		storageLocation = join( CONFIG.local_storage, str(newID) )
		if not os.path.isdir( storageLocation ):
			trace( "Generated ID %d, storage at %s" % (newID, storageLocation) )
			os.makedirs( storageLocation )
			break
		newID += 1

	return newID, storageLocation



def main():
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