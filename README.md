# CheckEvara

CheckEvara is a python script that is able to get your moodle courses and then get all Check Presence for a class. Then it will launch a notification daemon who will send you notifications for each Check Presence

The program will send you a notification to inform you that the notification daemon started

It will also add to fake Check Presence, one 15 seconds after notification daemon start and another 1 minute after

It can be used as follow:
```bash
./check-evara.py
```

The logs are available at `/tmp/CheckEvara.log`

It ask you your Moodle Session Cookie, you can watch the following example to see how to get it:
![example](./assets/get_moodle_cookie_example.gif)
