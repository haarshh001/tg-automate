# Telegram Auto-Forwarder & DiskWala Link Converter

This bot automatically monitors posts in a source Telegram channel, extracts DiskWala (or any other) URLs, sends them to the converter bot (`@DW2DW_LinkConverterBot`), and posts the converted URL along with the original photo/video/media to your own channel.

---

## What was verified and tested
1. **Existing Session**: Detected `harsh.session` in this folder. It is logged in as `Harsh (@haarshh001)`.
2. **Converter Bot**: Successfully tested with `@DW2DW_LinkConverterBot`. The bot responds in ~2-3 seconds with your personalized converted link.
3. **End-to-End Dry Run**: Tested against the exact post from your screenshot (`https://www.diskwala.com/app/6a79574206ba7ea03d63c8d0`), and it properly converted the URL and detected the attached photo.

---

## How to Configure

Open [`auto_converter.py`](auto_converter.py) and update the configuration section at the top:

```python
# Source channel(s) to monitor (can be numeric ID or username string):
SOURCE_CHANNELS = [
    -1003801941219,  # e.g., "Panjabhi bhabhi" or any channel
]

# Destination channel where converted posts will be sent:
TARGET_CHANNEL = -1004333951561  # e.g., @genz454 or your destination channel
```

---

## How to Run

### 1. Dry Run (Test without posting)
Tests link extraction and conversion on the latest post in the source channel without publishing:
```bash
python auto_converter.py --dry-run
```

### 2. Live Monitoring (Real-time listener)
Runs continuously in the background and processes any new post instantly:
```bash
python auto_converter.py
```
