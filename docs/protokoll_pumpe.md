

How to Control the Longer WT600-2J(1J)(3J) Pump via Matlab ?



&#x20;   Home

&#x20;   Tutorials

&#x20;   How to Control the Longer WT600-2J(1J)(3J) Pump via Matlab ?



TABLE OF CONTENTS



&#x20;   What do you need to communicate with the WT600-2J ?

&#x20;   How to Set Up the Communication Port ?

&#x20;   How to Write Control Command Strings to the WT600-2J ?

&#x20;       Set running parameter (rotation speed)

&#x20;       Read running parameter (rotation speed)

&#x20;       Write pump address

&#x20;       Read pump address

&#x20;       Examples of control command strings

&#x20;   How to communicate with the WT600-2J using Matlab ?

&#x20;   Conclusion



All our knowledgedistilled directly into your mailbox.

SUBSCRIBE TO OUR NEWSLETTER!

All our knowledgedistilled directly into your mailbox.DON'T MISS A SINGLE DROP!

Elia Missi Elia Missi

Tutorials

6 March 2024



If you are looking for a powerful peristaltic pump designed for laboratory and industrial applications, you might want to check out the Longer WT600-2J. This pump can deliver flow rates ranging between 4.2 mL/min and 6000 mL/min. It has a high torque maintenance-free brushless motor that allows mounting up to 4 pump heads on the same driver.



The WT600-2J can be controlled remotely from your computer which can give you more flexibility and convenience, especially if you want to run complex pumping programs with loops, pauses, and varying rotation speeds.



In this blog post, we will show you how to communicate with the WT600-2J using the LONGER RS485 protocol, which is a serial communication protocol that allows you to send commands and receive responses from the pump. We will also provide some examples and code snippets on how to use Matlab to write and send control command strings to the pump.

TABLE OF CONTENTS



&#x20;   What do you need to communicate with the WT600-2J ?

&#x20;   How to Set Up the Communication Port ?

&#x20;   How to Write Control Command Strings to the WT600-2J ?

&#x20;       Set running parameter (rotation speed)

&#x20;       Read running parameter (rotation speed)

&#x20;       Write pump address

&#x20;       Read pump address

&#x20;       Examples of control command strings

&#x20;   How to communicate with the WT600-2J using Matlab ?

&#x20;   Conclusion



What do you need to communicate with the WT600-2J ?



To communicate with the WT600-2J using the LONGER RS485 protocol, you will need the following:



&#x20;   A WT600-2J pump with a pump head and a tubing of your choice

&#x20;   A RS485 control module that plugs into the DB15 port on the rear of the pump

&#x20;   A serial cable that connects the RS485 control module to your computer or device

&#x20;   A programming platform (Matlab in the case herein)

&#x20;   A basic understanding of the data format, command format, and pdu format of the LONGER RS485 protocol (explained below 👇)



LOOKING FOR FLEXIBILITY IN TUBING OPTIONS?

Discover our selection!

LOOKING FOR FLEXIBILITY IN TUBING OPTIONS?

Explore our microfluidic tubing solutions for reliable and efficient flow in your experiments!

How to Set Up the Communication Port ?



Before you can start sending and receiving data from the pump, you need to set up the communication port correctly. Here are the steps to follow:



&#x20;   Connect the DB15 connector to the DB15 port on the rear of the pump

&#x20;   Turn on the pump

&#x20;   Make sure the communication parameters on your programming platform match the ones of the WT600-2J, which are:

&#x20;       1 start bit

&#x20;       8 data bits

&#x20;       1 even parity

&#x20;       1 stop bit

&#x20;       a baud rate of 1200 bits/s



How to Write Control Command Strings to the WT600-2J ?



Once you have set up the communication port, you can start writing and sending control command strings to the pump. A control command string is a sequence of hexadecimal characters that follows a specific format, which consists of:



&#x20;   a start flag (E9H)

&#x20;   a pump address (1 to 30, or 31 for broadcast)

&#x20;   a length of the pdu (protocol data unit)

&#x20;   a pdu, which contains the command characters and the parameters for the desired application

&#x20;   a frame check sequence (fcs), which is obtained by calculating the XOR of the pump address, the length of the pdu, and the pdu itself (compute your fcs using our online frame check sequence XOR calculator)



The pdu and its length depend on the application requested from the pump. The common applications are:



&#x20;   Set running parameter (rotation speed)

&#x20;   Read running parameter (rotation speed)

&#x20;   Write pump address

&#x20;   Read pump address



For each application, there is a corresponding set of command characters and parameters that you need to include in the pdu. These parameters are detailed below.

Set running parameter (rotation speed)



This application consists of writing to the pump. The overall length of the pdu is 6 bytes where the control command string consists of (in the exact same order):

WJ	Set Speed	State 1	State 2

2 bytes	2 bytes	1 byte	1 byte



&#x20;   WJ, control command string of 2 bytes, 57 4A

&#x20;   Set rotation speed (2 bytes) with a maximum speed of 600 rpm (02 58)

&#x20;   State 1 (1 byte): 

&#x20;       bit 0 – start/stop bit where 1 is to start the pump and 0 is to stop it

&#x20;       bit 1 – prime bit where 1 is to prime the pump at the max speed of 600 rpm and 0 is to run the pump at a normal speed

&#x20;   State 2 (1 byte):

&#x20;       bit 0 – sets the rotation direction where 1 is for clockwise and 0 is for counter-clockwise



The pump will respond with WJ and will display on its front screen the rotation speed after receiving the control command string.

Read running parameter (rotation speed)



This application consists of reading from the pump. The overall length of the pdu is 2 bytes where the control command string is RJ.



The pump’s response consists of:

RJ	Show Speed	State 1	State 2

2 bytes	2 bytes	1 byte	1 byte



&#x20;   RJ, control command string of 2 bytes, 52 4A



Write pump address



This application consists of writing to the pump. The overall length of the pdu is 4 bytes where the control command string consists of:

WID	New pump I.D.#.

3 bytes	1 byte



&#x20;   WID, control command string of 3 bytes, 57 49 44

&#x20;   New pump address (1 byte), can be pump address (1-30) or broadcast address (31); the default pump address is 1



The pump will respond with WID.

Read pump address



This application consists of reading from the pump. The overall length of the pdu is 3 bytes where the control command string is RID.



In a command string from the control computer, if the address is one pump’s address (1-30), not the broadcast address (31), the corresponding pump will respond with RID.

Examples of control command strings



&#x20;   Set the WT600-2J to run clockwise at a rotating speed of 150 rpm



Control command string: E9 01 06 57 4A 00 96 01 01 8C



&#x20;   E9 as the flag

&#x20;   01 as the address 1 of the pump

&#x20;   06 as the length of the pdu (57 4A 00 96 01 01)

&#x20;   57 4A as command characters WJ

&#x20;   00 96 refers to the rotation speed, 0096(hex) = 150(dec) (check our online base conversion tool)

&#x20;   01 to start the pump at normal speed

&#x20;   01 to run the pump clockwise

&#x20;   8C as the XOR result of 01 (pump address), 06 (pdu length) and 57 4A 00 96 01 01 (pdu) 



&#x20;   Set the address (initially 1) of the WT600-2J to address 7



Control command string: E9 01 04 57 49 44 07 58



&#x20;   E9 as the flag

&#x20;   01 as the initial address 1 of the pump

&#x20;   04 as the length of the pdu (57 49 44 07)

&#x20;   57 49 44 as command characters WID

&#x20;   07  as the new pump address

&#x20;   58 as the XOR result of 01 (pump address), 04 (pdu length) and 57 49 44 07 (pdu) 



🚨Do not hesitate to use our user-friendly online command string generator to effortlessly generate precise control command strings for your WT600-2J.

How to communicate with the WT600-2J using Matlab ?



Matlab code snippets showing how to open the serial port, write and send control command strings to the pump and write a simple pumping program are presented below.



From the first example just presented above, the following Matlab code snippet makes the WT600-2J run clockwise at a rotating speed of 150 rpm.



%%% RUN PUMP 1, CLOCKWISE, AT A ROTATING SPEED OF 150 RPM



% Open the serial port with the data format corresponding to the WT600-2J

s = serialport('COM6', 1200, 'Parity', 'Even', 'DataBits', 8, 'StopBits', 1);



% Write the corresponding control command string

Str = 'E9 01 06 57 4A 00 96 01 01 8C';



% Read data from Str, convert it according to the format specified '%2x' (hexadecimal conversion), transpose and return the results in an array

Data = sscanf(Str, '%2x').';



% Write the Data to the pump in the form of an unsigned integer 8bits

write(s, Data, uint8);



&#x20;   In a second code snippet, let’s make the pump (address 4) run clockwise at a rotating speed of 320 rpm for 10s, then make it run counter-clockwise at a rotating speed of 50 rpm for 30s before stopping it.



%%% RUN PUMP 4 CLOCKWISE AT A ROTATING SPEED OF 320 RPM FOR 10s, THEN COUNTER\&minus;CLOCKWISE AT A ROTATING SPEED OF 50 RPM FOR 30s BEFORE STOPPING IT



% Open the serial port with the data format corresponding to the WT600-2J

s = serialport('COM6', 1200, 'Parity', 'Even', 'DataBits', 8, 'StopBits', 1);



% Run pump 4 clockwise at a rotating speed of 320 rpm for 10s

Str = 'E9 04 06 57 4A 01 40 01 01 5E'; % 320 (dec) = 01 40 (hex)

Data = sscanf(Str, '%2x').';

write(s, Data, uint8); % write the Data to the pump



Pumping\_time = 10;

while Pumping\_time \&gt; 0

&#x20;   pause(1)

&#x20;   Pumping\_time = Pumping\_time \&minus; 1;

&#x20;   disp(\['Remaining\_time:' num2str(Pumping\_time)])

end % 10s delay with a visible timer



% Run pump 4 counter-clockwise at a rotating speed of 50 rpm for 30s

Str = 'E9 04 06 57 4A 00 32 01 00 2C'; % 50 (dec) = 00 32 (hex)

Data = sscanf(Str, '%2x').';

write(s, Data, uint8); % write the Data to the pump



Pumping\_time = 30;

while Pumping\_time \&gt; 0

&#x20;   pause(1)

&#x20;   Pumping\_time = Pumping\_time \&minus; 1;

&#x20;   disp(\['Remaining\_time:' num2str(Pumping\_time)])

end % 30s delay with a visible timer



% Stop the pump

Str = 'E9 04 06 57 4A 00 32 00 00 2D'; % corresponding control command string; we took the previous command string and changed the State 1 byte from 01 (start the pump) to 00 (stop the pump) and of course computed the new fcs

Data = sscanf(Str, '%2x').';

write(s, Data, uint8); % write the Data to the pump



Conclusion



We hope this blog post has helped you understand how to control the Longer WT600-2J multichannel peristaltic pump remotely via Matlab using the LONGER RS485 protocol. You can also use other programming platforms such as Python to write and send control command strings to the pump and read and interpret the responses from the pump. For more details about this topic, check our blog post “How to Control the Longer WT600-2J(1J)(3J) Pump via Python ?”.



