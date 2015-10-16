import os
import sys
import subprocess
import shutil


STATUS_NAMES = {
	'?': "unversioned",
	"I": "ignored",
}

path = sys.argv[1]

os.system( 'svn revert -R "%s"' % path )

output = subprocess.check_output(['svn', 'status', '--no-ignore', '%s' % path])
for line in [ x.strip() for x in output.splitlines() if len(x.strip()) > 0 ]:
	if line[0] not in STATUS_NAMES.keys():
		continue
	
	status = STATUS_NAMES[line[0]]

	filename = line[1:].strip()

	if os.path.isfile( filename ):
		try:
			os.remove( filename )
			print 'Deleted %s file \'%s\'' % (status, filename)
		except Exception, e:
			print 'Failed to delete file \'%s\'' % filename
			print '\t', str(e)
	elif os.path.isdir( filename ):
		try:
			shutil.rmtree( filename )
			print 'Deleted %s directory \'%s\'' % (status, filename)
		except Exception, e:
			print 'Failed to delete directory \'%s\'' % filename
			print '\t', str(e)
		
