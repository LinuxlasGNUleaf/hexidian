# hexidian
An event broker between [GURU3](https://github.com/eventphone/guru3) (frontend self-registration software for consumers), [Asterisk](https://github.com/asterisk/asterisk) (PBX software) and the Mitel Open Mobility Manager (DECT antenna and handset manager), which is accessed via [python-mitel](https://github.com/dect-e/python-mitel).

## How does it work?

### GURU3 event management
*hexidian's* main task is to listen for incoming new events from the Self-Registration-Frontend GURU3. These events are created whenever a user creates a new "extension" (call number) or changes an exisiting one in their account.
When a new event is created, *hexidian* is notified of this via a websocket connection. The actual event however has to be queried via the REST API of Guru3. The event then gets processed and routed by *hexidian*, depending on
which kind of extension they are about: If it is about a DECT-handset, the event will in some way result in a command sent to the Open Mobility Manager via python-mitel. Since all extensions, even the DECT-handsets,
have a connected SIP user, most events will also be sent to the PBX software Asterisk. This is done indirectly, by modifying the PostgreSQL database Asterisk operates on.
After the event is fully processed, it is reported complete to Guru3 via a POST request.

### unbound handset processing
In addition, *hexidian*  will search for newly subscribed handsets in DECT network, which are not yet assigned to *any* user. It will assign them a temporary user in a seperate call-group, which allows the handset to call a specific subset of all available numbers (more on that in a second). These are reffered to as "Unbound Handsets". Every DECT-type extension in GURU3 has a "token"-telephone number. if the user calls this number with his subscribed, but currently unbound handset, Asterisk will register this call and send a POST request to *hexidian* (which also runs a webserver for exactly this purpose) with info about the caller (the temporary user assigned to the unbound handset) and the token number called. *hexidian* can now work out which user this handset should be linked to, and make the necessary changes in the Open Mobility Manager. The temporary user can now be deleted, since the handset is now connected.

## Credits
written by Jakob Weiß and Luca Lutz for the November Geekend 23

### Many thanks to:
- **Eventphone** for making [Guru3](https://github.com/eventphone/guru3) public, without which this project would have been utterly impossible.
- **Experimentiergruppe DECT** for creating the [python-mitel](https://github.com/dect-e/python-mitel) library, which made dealing with the OMM an absolute breeze.