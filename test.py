

from slack_integration.slack_client import SlackClient
sc = SlackClient(token, channel_id)

# Post a dummy thread
parent_ts = sc.create_thread("*DEBUG* parent message")
print("parent_ts =", parent_ts)

# Simulate the tutor’s answer
ok = sc.post_to_thread(parent_ts, "Hello from local test")
print("post_to_thread returned", ok)
