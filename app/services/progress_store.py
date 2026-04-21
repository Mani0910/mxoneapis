progress_data = {
    "task": "",            # transfer | upgrade
    "current_step": "",    # current logical step name
    "state": "idle",       # idle | connecting | in_progress | rebooting | completed | error
    "progress": 0,         # 0-100 percent
    "message": "",         # human-readable status
    "in_progress": 0,      # 1 while transfer is running
}