# hexidian
An event broker between [Guru3](https://github.com/eventphone/guru3), [Asterisk](https://github.com/asterisk/asterisk) and the Mitel Open Mobility Manager (accessed via [python-mitel](https://github.com/dect-e/python-mitel)).

## How does it work?
*hexidian's* main task is to listen for incoming new events from the Self-Registration-Frontend GURU3, which it receives a notification about via a websocket and queries via the REST API of Guru3. These events then get processed, depending on
which kind of extension they are about, by either sending commands to the Open Mobility Manager via python-mitel or to Asterisk via its PostgreSQL database, or both. After they are processed, they are reported complete to Guru3 via POST request.
In addition, *hexidian*  will search for new unbound handsets subscribed to the DECT network and will assign them a temporary user in a seperate call-group. Once these unbound handsets call their token-number (which is used to link them to the extension created in Guru3), *hexidian* will receive a POST request on the webserver its running containing a JSON with the caller's number and the token called. This info is then used to link the Portable Part to its user in the Open Mobility Manger.

## Credits
written by Jakob Weiß and Luca Lutz for the November Geekend 23

many thanks to:
- **Eventphone** for making [Guru3](https://github.com/eventphone/guru3) public, without which this project would have been utterly impossible.
- **Experimentiergruppe DECT** for creating the [python-mitel](https://github.com/dect-e/python-mitel) library, which made dealing with the OMM an absolute breeze.