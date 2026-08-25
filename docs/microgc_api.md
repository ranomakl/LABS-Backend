from MicroGCFusionAPI import Fusion



\#Enter Micro GC Fusion IP Address (Ex: 10.10.0.1)

f = Fusion('10.10.0.1')



\#Return connected status (True / False):

f.connected()



\#Return instrument status ( {'sequence': 'public:sequence-not-loaded', 'system': 'public:ready'})

status = f.status()

sequenceStatus = status\['sequence']

systemStatus = status\['system']

'''

Avalible Status Options: 

System States:

\----------------------------------

public:bakeout

public:error-carrier-gas-pressure

public:error-method-load-failed

public:error-running-too-long

public:loading-method

public:manual-purge

public:method-running

public:preparing

public:ready

public:shutdown

public:standby

public:waiting-for-modules





Sequence States:

\---------------------------------

public:error-event-sequencer-down

public:sequence-loaded

public:sequence-not-loaded

public:sequence-running





Possible Error States

\---------------------------------

public:error-moduleA

public:error-moduleB

public:error-moduleC

public:error-moduleD

public:error-system-uninitialized

public:uninitialized



'''



\################################################## Info #############################################################

\#Subclasss of Fusion that provides information about the system



&#x20;   #Return the system serial number (return: '70000001')

&#x20;   f.info.serialNumber()



&#x20;   #Retrun the system part number (return: 'F08504W02W02')

&#x20;   f.info.partNumber()

&#x20;   

&#x20;   #Return the system host name (return: 'NatGas2')

&#x20;   f.info.hostname()



&#x20;   #Return the system storage limit status (return: 'ok', 'approaching', 'exceeded')

&#x20;   f.info.storageLimit()



\################################################## Network ##########################################################

\#Subclass of Fusion that provides networking information

&#x20;   

&#x20;   #Return the networking information in JSON format:

&#x20;    f.network.info()

&#x20;   #Return Example:

&#x20;   '''

&#x20;       {'IPAddress': \['10.215.38.131'],

&#x20;           'date': 1725973498712,

&#x20;           'dhcpAddress': '10.215.38.131',

&#x20;           'hostname': 'NatGas2',

&#x20;           'macAddress': {'eth0': 'XX:XX:XX:XX:XX:XX', 'wlan0': 'XX:XX:XX:XX:XX:XX'},

&#x20;           'staticIP': {'address': '10.10.1.12',

&#x20;               'enabled': False,

&#x20;               'gateway': '',

&#x20;               'subnet': '255.255.0.0'},

&#x20;           'wifiEnable': True,

&#x20;           'wifiPassword': 'inficongc'}

&#x20;   '''

&#x20;  



&#x20;   #Enable / Disable the wifi using the toggle wifi command.

&#x20;   #Returns the current state of the system after toggle (return: True / False)

&#x20;   f.network.toggleWifi()



&#x20;   #Get the current Wifi password of the system (return: 'inficongc')

&#x20;   f.network.getWifiPassword()



&#x20;   #Set the wifi password of the system:

&#x20;   f.network.setWifiPassword('NewWifiPassword')



&#x20;   #Set the hostname of the system:

&#x20;   f.network.setHostname('NewHostName')



&#x20;   #Sync the system time to local computer:

&#x20;   f.network.syncTime()



\################################################## Control ##########################################################

\#Subclass of Fusion that provides control over the system

&#x20;   

&#x20;   #Run the system when ready:

&#x20;   f.control.run()



&#x20;   #Run with run name and tags (input options: Name, \[tags])

&#x20;   f.control.runWithName('SampleName',\['tagOne','tagTwo','tagThree'])



&#x20;   #Stop a sequence in progress (the current run will run through completion)

&#x20;   f.control.stopSequence()



&#x20;   #Abort a current run and/or sequence immediately. Note this may cause future chromatography issues and is not recommended.

&#x20;   f.control.abortCurrentRun()



&#x20;   #Load a specific method using the method name:

&#x20;   f.control.loadMethod('nameOfMethod')



&#x20;   #Load a specifi sequence using the sequence name:

&#x20;   f.control.loadSequence('nameOfSequence')



&#x20;   #Reboot the system immediately

&#x20;   f.control.reboot()



&#x20;   #Start a bakeout procedure specified in minutes. Default is 30 minutes

&#x20;   f.control.bakeout(minutes=120)



&#x20;   #Send a get request with any string after ip address. Ex: https//10.215.38.3{string} where {string} = /v1/lastRun (return: JSON object)

&#x20;   f.control.getStringCommand('string')



\################################################## Methods ##########################################################

\#Subclass of Fusion that provides access to the user methods on the system



&#x20;   #Retrun all of the methods on the system in JSON structure, listed by method name

&#x20;   f.methods.getAll()



&#x20;   #Return a specific method by providing a method name

&#x20;   f.methods.get('nameOfMethod')



&#x20;   #Create a default method based on the system part number. These methods were created by INFICON GC experts and are a better starting point (Returns: name of new method)

&#x20;   f.methods.methodByPN()



\################################################## Module ###########################################################

\#Subclass of Fusion that provides access to individual module information

\#This subclass requires the user to know the system configuration and which modules are installed in the system

&#x20;   #Return serial number of each module in the system (Ex: 4 module system)

&#x20;   f.moduleA.serialNumber()

&#x20;   f.moduleB.serialNumber()

&#x20;   f.moduleC.serialNumber()

&#x20;   f.moduleD.serialnumber()

&#x20;   #The rest of the examples will use "moduleA" as an example



&#x20;   #Return the module information in a dictionary, (return Information: column type, injector, detector)

&#x20;   f.moduleA.info()

&#x20;   #Return Example:

&#x20;   '''

&#x20;   {'column': 'Rt-Molsieve 5A, 0.25mm (10m) \[Rt-Q-BOND (3m)]',

&#x20;   'detector': 'TCD2',

&#x20;   'injector': 'Backflush 1.0 uL',

&#x20;   'reserved': '0'}

&#x20;   '''

&#x20;   #Return module serial number (return: '70094396')

&#x20;   f.moduleA.serialNumber()



&#x20;   #Return module part number (return: 'W02')

&#x20;   f.moduleA.partNumber()



&#x20;   #Return state of all module heaters in a dictionary

&#x20;   f.moduleA.heaters()

&#x20;   #Return Example:

&#x20;   '''

&#x20;   {'columnHeater': 59.98,

&#x20;   'externalColumnHeater': 60.0,

&#x20;   'flowManifoldHeater': 55.07,

&#x20;   'injectorDieHeater': 89.7,

&#x20;   'tcdHeater': 61.13}

&#x20;   '''



&#x20;   #Return current pressure(s) of the module

&#x20;   f.moduleA.pressures()

&#x20;   #Retrun Example:

&#x20;   '''

&#x20;   {'carrier': 20.0, 

&#x20;   'inject': 0}

&#x20;   '''



&#x20;   #Return the raw TCD signal from the module (return: -188591.42065048218)

&#x20;   f.moduleA.tcdSignal()



&#x20;   #Return the current valve state (0 = inactive, 0.5 = active)

&#x20;   f.moduleA.valves()

&#x20;   #Return Ex:

&#x20;   '''

&#x20;   {'backflush': 0, 

&#x20;   'forflush': 0, 

&#x20;   'inject': 0, 

&#x20;   'sample': 0.5, 

&#x20;   'switch': 0}

&#x20;   '''



&#x20;   #Return fan duty cycle (1 = 100%)

&#x20;   f.moduleA.fan()



\################################################## Databrowser ######################################################

\#Subclass of Fusion that provides access to the databrowser database.



&#x20;   #Return the full datafile of the last run in JSON format. Note, these datafiles have a significant amount of data in them.

&#x20;   f.data.lastRun()



&#x20;   #Return the run ID (UUID) of the last run.  This can be used to check if a new run is available ('ea9d0e98-c254-4481-a1aa-834ab2b8e38b')

&#x20;   f.data.lastRunID()



&#x20;   #Return the full datafiles of the last "X" number of runs. Note, a large X valves will take a significant amount of time to process.

&#x20;   f.data.getLastX(5) #grabs the last 5 runs in a list \[]



&#x20;   #Return datafile based on the run ID (uuid)

&#x20;   f.data.getData("e4aca6cd-e2a0-4148-bad3-bdbdefec4ee9")



&#x20;   #Return total number of runs in database

&#x20;   f.data.totalCount() #Returns integer \~ 21293



&#x20;   #Return based on the query text from the API guide:

&#x20;   f.data.queryText('text=foo\&sortByData=DESC') #Return a list of run IDs that contain the text "foo" sort that list in decending order

&#x20;   #Query Text Options:

&#x20;   '''

&#x20;   Query parameter	    Type	    Description

&#x20;   id	                String	    A string containing the id or pipe(|) delmited ids a document can contain

&#x20;   text	            String	    A string containing the text or pipe(|) delmited names a document can contain

&#x20;   date	            String	    ISO8601 string containing the date or pipe(|) delmited dates for when a run was executed.

&#x20;   startDate	        String	    ISO8601 string for runs after this date.

&#x20;   endDate	            String	    ISO8601 string for runs before this date.

&#x20;   startDateInclusive	boolean	    rue if the start date is inclusive (default), false otherwise.

&#x20;   endDateInclusive	boolean	    True if the end date is inclusive (default), false otherwise.

&#x20;   limit	            Integer	    The number of rows to be returned.

&#x20;   offset	            Integer	    The offset within the results set.

&#x20;   sortByDatum	        String	    The name of the field to sort on. Only one supported currently.

&#x20;   datumSortOrder	    String	    ASC or DESC to indicate the results should be sorted by a datum element in the document in that order.

&#x20;   sortByDate	        String	    ASC or DESC to indicate the results should be sorted by date in that order. (Default:DESC)

&#x20;   allData	            boolean	    Flag for whether or not to return all the data. Default: false.

&#x20;   includeData	        String	    The data field name to include in the return.

&#x20;   countOnly	        boolean	    Flag for whether or not to data, or the total number of rows in the data set. Default: false.

&#x20;   noId	            boolean	    Flag for whether or not to return $id in run. Default: false

&#x20;   updatedSince	    String	    ISO8601 string for runs updated after this date.

&#x20;   '''

&#x20;   

&#x20;   #Replace a data file to the database by providing the correct datafile JSON structure. Typically this is done by pulling data, modifying then returning

&#x20;   runData = f.data.lastRun()  #Pull the datafile of the last run

&#x20;   runData\['annotations']\['name'] = 'newSampleName' #Change the sample name by modifying the annotations/name section of the datafile 

&#x20;   f.data.replaceData(runData)  #Return the datafile to the databrowser with the updated sample name



&#x20;   #Add a new datafile to the databrowser, the run ID (uuid) cannot already be in the the databrowser or the upload will not work properly. 

&#x20;   f.data.addNewData(datafileInJsonStructure)

&#x20;   

&#x20;   #Reprocess a specific datafile by sending the run ID (uuid)

&#x20;   f.data.reprocess("e4aca6cd-e2a0-4148-bad3-bdbdefec4ee9")



&#x20;   #Reprocess several data files by providing a list of run IDs 

&#x20;   runIDList = \[

&#x20;       "e4aca6cd-e2a0-4148-bad3-bdbdefec4ee9",

&#x20;       "24b5d865-8ac9-4d68-99dc-719772ceb6c2",

&#x20;       "fa230e0e-5927-482a-a214-a696facc4bc2",

&#x20;       "3e9159d9-bcf8-4050-967b-1d18661bed65"

&#x20;   ]

&#x20;   f.data.reprocessMany(runIDList)



&#x20;   #Return a simplier version of the last run data file

&#x20;   f.data.compoundResults()

&#x20;   #Return Example:

&#x20;   '''



&#x20;   '''



\################################################## Valco ############################################################

\#Subclass of the Fusion enabling status and control of a connected Valco Stream Selector valve

&#x20;   

&#x20;   #Return a True / False if the valve is currently connected

&#x20;   f.valco.enabled()



&#x20;   #Return information about the valco valve in a JSON structure

&#x20;   f.valco.info()

&#x20;   #Return Example:

&#x20;   '''

&#x20;   {'dataRate': 9600, 

&#x20;   'mode': 3, 

&#x20;   'position': 1, 

&#x20;   'positions': \[1, 2, 3, 4]}

&#x20;   '''



&#x20;   #Return the current position of the valve (return: 4)

&#x20;   f.valco.getPos()



&#x20;   #Set the position of the valve changing it

&#x20;   f.valco.setPos(3) # change the valve postion to postion 3



\################################################## Notifications ####################################################

\#Subclass of the Fusion enabling messaging through notification system within the Micro GC Fusion GUI.

&#x20;   #Send Info message (Blue notification appears in bottom right of the GUI, will disappear after a few seconds)

&#x20;   f.notifications.info('this is an info message')



&#x20;   #Send Warning message (Yellow notification appears in the bottom right of the GUI, will stay until the GUI user removes it)

&#x20;   f.notifications.error("this is a warning message")

&#x20;   

&#x20;   #Send Error message (Red notification appears in the bottom right of the GUI, will stay until the GUI user removes it)

&#x20;   f.notifications.error('this is an error message')

