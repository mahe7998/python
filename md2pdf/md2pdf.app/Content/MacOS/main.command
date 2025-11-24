
#!/bin/sh

# main.command

#  Created by _yourname_
#  Copyright (c) 2010 _comapnyname_, All Rights Reserved.

# Get local path of Application
FILEPATH=$(dirname $0)
BASEPATH=${FILEPATH%/*/*/*}
echo $BASEPATH


# Insert shell script code
osascript -e 'tell app "Finder" to display dialog "Hello Cool IT Help"'

exit 0
