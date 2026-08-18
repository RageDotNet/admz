#### New Design (MVP)

##### Terms
action: an api endpoint that an agent serves and other agents can call.
client: agent that calls actions
provider: agent that registers and responds on actions
admin: human (?) administrator

# Old stuff

We are going to keep the following elements:
Requests come in, the same json schema and LLM judge is happening on request,response.

The webui can still be used to look at requests in different states, logs, client/provider.

# New stuff

Summary - DMZ now provides a directory of available actions. A client can request access to an action and if approved call the action. The action is processed and a response given to the client immediately. Providers can register and update their own actions. Administrators can approve actions and client access to actions & review logs of requests.


The config file is now a YAML that defines config for the system. Agents are registered in the webui by an admin, and given a bearer key. agent can be a client, a provider, or both. each agent has a bearer key associated with it. providers must have an endpoint, it should specify protocol to use (such as 'completions', or 'exec', or 'post') a config for the protocol, ie 'completions' endpoint specified for it, and that should show the URL to hit, an array of header/values to send.. for exec endpoints it simply opens a pipe to the defined program puts the input on stdin, and reads the output from stdout till the program ends.. For post, it includes a url and headers, and simply posts the input, and reads the output.

admins can have user/pass and also a bearer token. there can be multiple admins. In this version they are defined in the config file.

Agents can have the role client or provider. providers offer actions. Providers can offer actions, they have the state submitted, active (approved), rejected. There is a REST api that clients can do CRUD operations on actions. When a provider edits a action, there is a versioned thing of it, the old version is active until the new version is approved by the administrator. deletes can happen immediately (although delete just deactivates the action and makes it unavailable for discovery or invocation).

A rest directory where a client can request to see all available actions.. it can see which actions that are available, ones it requested access to but is not approved, ones where access request was rejected, and ones which it is approved for. The webui has a thing for admins to manage access requests to services. Admins can also have a view of the directory of all available actions.

There is a /skill endpoint that has two skills, one for clients another for providers.

There is no 'manual' or 'quarantine' state for a request. each request is processed immediately. When a client makes a request, if there is either a schema or a arbiter rejection the client is told immediately. When the request is handed to the provider, if the provider response has a schema or arbiter failure, it is retried a configured amount of times (2 default). If it fails all times then the client gets a response that the provider failed to provide a valid response.

For long-running processes, the provider should queue the work, respond with a request tracking id, and provide either a polling endpoint to return the request, or the client should have its own provider action to receive a result.
