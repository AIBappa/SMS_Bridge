Key updates required are as follows:

Functionality to be targeted:
1) The tests folder should be updated to show a small dummy onboarding sequence on the UI. This can be a localhost applicaiton that i can run as a webapp on my mobile. This can be via the test_app.py file update or maybe a seperate file (choose the option which you feel is reversible and does not interfere with existing test function achieved). The onboarding sequence is as follows.
a. User enters a mobile number to validate. This is a ten digit Indian mobile number.
b. Once entered, an API call is made to the backend (new file could be created or update for sms_server.py). A hash generator uses the hash_secret_key from vault.yml to create a hash for the entered mobile number + time (Indian standard time) + date of recieving validation request. The time and date act as 'salt'. 
c. Hash is then posted back to the frontend where user sees a message. ONBOARD:<hash_generated>
d. User also sees instructions to "SMS this hash alongwith the number entered to a number 90XXXXYYYY. Once button below clicked an SMS applicaiton will start. Press the send button without updating any number or text".
e. A button is also shown below this. When clicked, the SMS applicaiton shall be invoked with the to number as in step d. and the message as in step c.
f. From step b, schema.sql needs to be updated to include an onboarding_mobile table. This will include the mobile number, time/date of recieving mobile number from the UI and the hash key generated. So 4 columns as a minimum. Any other columns that are must or industry standard, please inform and directly update.

2) Update checks in the checks folder:
g. Introduce a new check foriegn_number. This is to ensure that only SMSes from a configured national domain are sent for further checks. The configuration should be via the settings table in schema.sql. for e.g. to only process India numbers, the allowed SMSes should be from +91 or 0091 (this is phone code for India, and configurable from settings). It should also be possible to sequnence this check and enable/disable this check via settings, as the other checks.
h. Header+hash_length check for recieved SMS in input_sms table from schema.sql should be combined. For e.g. allowable header like ONBOARD from step c should be checked alongwith the remainder of the hash length. Because the length of the SMS message - this includes the header and hash is to be checked. The allowable header should be derived from settings table.
i. mobile_check should be between recieved SMS number in input_sms versus the onboarding_mobile. Check passes if hash sent via step b and recorded in onboarding_mobile table is checked versus hash recieved in SMS message in input_sms dataset AND corresponding mobile numbers match as well.
j. time_window check should be between recieved time/date of mobile number request in onboarding_mobile table versus the time of recieving SMS in input_sms table.