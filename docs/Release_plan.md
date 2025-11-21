The following system block diagram shows the various aspects of the SMS_Bridge proposed for Production_2.
The objective is to have a production ready system with less of PostgreSQL and more of Redis to provide a faster experience to the user (Redis) plus cater for backup, reliability and audits.

Legend is as follows:
1) The frontend part of the system is shown in Blue.
2) Cloudflare Hono in Green
3) Local Redis in Orange
4) Local PostgreSQL in Yellow
5) Hetzner Supabase in Cream.

<img width="1710" height="803" alt="Mobile_Validation_System" src="https://github.com/user-attachments/assets/a5f00579-e9e2-479a-97cb-0e3f8a256410" />

The system caters to the following user case scenarios.

Use case 1) The general workflow is from the user end, user sends details to onboard which include mobile number, device ID , email and the time of application.
This information passes via CF , through a local tunnel to local Redis, where a hash is generated and fed back to the user alongwith a mobile number where hash can be sent and confirmed. This is supposed to be done within a timelimit.
User then sends SMS to the recieving number with the Hash to confirm mobile number. Sending Hash from the same mobile number as that provided to generarate Hash will allow confirmation, plus costs for sending SMS from application end can be avoided.
Once the SMS reaches the local reciever, it is parsed and undergoes a series of checks to be confirmed.

Use case 2) Malicious users who send SMS to the recieving number will be inherently prohibited because it will cost them to send SMS. Also even if they do send SMSes, because the checks are in Redis, it should prevent an impact on the Supabase Hetzner.
Malicious users that send fake mobile numbers over IP, those mobiles cannot be registered unless SMS is recieved with hash. Also if they send multiple spurious mobiles numbers, IP rate limiting at CF end will protect from multiple requests.
These requests will also be captured in PostgreSQL locally to audit and report wherever necessary.

Use case 3) Local issues - Power loss and local server not reachable. In this case, Mobile number will still operate and recieve SMSes. The weblink between the mobile and the local server will break, however this can be tracked to understand which SMSes
were recieved and when power is resurrected, those SMSes can be pushed back on the weblink. Potential update to mobile software reciever (Android) could be required. However, a manual push from mobile is also possible. Health tracker will also push message
to User over IP that mobile onboarding is currently paused due to server issue.

User case 4) Local issues - Redis down but PostgreSQL still working. In this scenario, PostgreSQL has power down table to save local SMSes from mobile. These will be pushed to Redis when Redis is brought back on.

Requirements for Local Server - Python core
1) Have a UI for SMS_Settings table, so that these settings can be changed by user directly on local machine.
2) Read SMS Recieved as per Swagger API call and add it to the Queue_input_sms table in Redis. This table is kept updated with the results of the various checks that the SMS (message + number) undergo.
3) The checks are enabled as per the SMS_Settings table enable/disable check. If check disabled, the next enabled check shall be proceeded with. If check disabled, that field in Queue_input_sms should be "disabled". If one check fails, the next checks are not required and should be noted "N/A".
4) If the hash recieved and the hash generated tally and their mobile numbers tally as well, the mobile is considered validated. Accordingly the row in the Queue_input_sms shall be updated.
5) 
