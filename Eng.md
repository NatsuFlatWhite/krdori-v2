<p align="center">
  <a href="https://github.com/NatsuFlatWhite/krdori-v2">한국어</a>
  |
  <b>English</b>
</p>

# krdori-v2

**krdori-v2** is an unofficial local server implementation for the Korean version of *BanG Dream! Girls Band Party!*, commonly known as **KRdori**.

It is based on [RainbowUnicorn7297/krdori-local](https://github.com/RainbowUnicorn7297/krdori-local) and adds previously unimplemented APIs, local state persistence, and support for several systems that did not function correctly in the original project.

> This project is a non-commercial project created for game server protocol analysis, research into in-game packet processing, and local environment testing.  
> It is an unofficial project with no affiliation with Bushiroad, BanG Dream!, or any related rights holders. Official resources, including the game APK, are not provided.

This repository does not include any of the following:

* The game application or any official game resources
* Real user accounts, personal information, or authentication credentials
* Features for connecting to official servers or bypassing official authentication

---

## Features

### Free Live

* Supports Free Live entry and session handling.
* Manages live start and completion states.
* Stores play results and high scores.
* Applies combo count, clear status, and score rank results.

### Live Results and Rewards

* Calculates scores and rewards after completing a live session.
* Applies different reward multipliers based on the amount of Live Boost consumed.
* Awards coins, items, rank experience, and event points.
* Stores high scores and clear records for each song.

### Live Boost

* Recovers Live Boost every 30 minutes based on server time.
* Consumes Live Boost according to the multiplier selected before starting a live session.
* Supports recovery using boost recovery items and Stars.
* Stores the remaining Live Boost amount and the next recovery time.

### Area Items

* Supports purchasing Area Items.
* Supports upgrading Area Item levels.
* Allows Area Items to be installed and replaced in each area.
* Permanently stores installed Area Item states.

### Profile Management

* Allows users to change their name and profile message.
* Supports selecting a featured character and illustration.
* Supports changing main and sub titles.
* Supports changing profile frames and pins.
* Stores profile visibility settings.

### Band and Deck Management

* Supports changing the main band.
* Supports changing band member compositions.
* Stores standard decks and event-specific decks.
* Preserves deck names and composition preset states.

### High Score Rating

* Stores high scores for each song and difficulty.
* Calculates high score ratings for each band.
* Applies calculated rating results to profile and mission data.

### Daily Login Bonus

* Determines daily login status based on Korea Standard Time.
* Stores login bonus progression.
* Prevents duplicate rewards from being claimed on the same day.
* Grants the reward corresponding to the current progression day on the first login of each day, using a set of seven predefined rewards.

### Missions

* Updates mission progress according to predefined conditions.
* Supports claiming rewards from completed missions.
* Stores mission progress and reward claim states.

### Local State Persistence

Mutable user data is stored in a SQLite database.

The default database location is:

```text
state/db.sqlite3
```

---

## Server Architecture

Running `main.py` starts the following three server components:

| Server         | Default Port | Protocol  | Role                                                              |
| -------------- | -----------: | --------- | ----------------------------------------------------------------- |
| Kakao Server   |       `8480` | HTTP      | Handles authentication and SDK requests.                          |
| Session Server |       `8481` | WebSocket | Handles login sessions and game session communication.            |
| Game Server    |       `8482` | HTTP      | Handles game data, live sessions, decks, profiles, and Area APIs. |

The Kakao Server and Game Server run as separate child processes, while the Session Server runs in the main process.

---

## Client Compatibility

This server is not directly compatible with an unmodified official game client.

The Kakao Server, Session Server, and Game Server addresses in the client must be changed to point to the local server.

The Session Server must also be configured to use a WebSocket connection compatible with the current server implementation.

---

## Requirements

* Python 3
* Git
* An Android device or emulator
* Termux or a PC environment capable of running Python

The following Python packages are required:

```text
websockets
protobuf
pycryptodome
flask
```

---

## Running on Termux

This method runs both the server and game client on the same Android device.

```bash
pkg update -y
pkg install -y git python

git clone https://github.com/NatsuFlatWhite/krdori-v2.git
cd krdori-v2

python -m venv env
source env/bin/activate

python -m pip install --upgrade pip
python -m pip install websockets protobuf pycryptodome flask

python main.py
```

The client server addresses must point to the local address of the Android device.

```text
127.0.0.1:8480
127.0.0.1:8481
127.0.0.1:8482
```

---

## Using setup.sh

The following commands can be used to automate the installation and startup process:

```bash
curl -L https://raw.githubusercontent.com/NatsuFlatWhite/krdori-v2/main/setup.sh -o setup.sh
chmod +x setup.sh
./setup.sh
```

`setup.sh` installs the required packages, creates a Python virtual environment, and starts the server in the background.

To stop the server, run:

```bash
pkill -f "python main.py"
```

---

## Running on PC with ADB Reverse

When running the server on a PC, each port must be forwarded using ADB Reverse so that the Android client can connect through `127.0.0.1`.

```bash
adb reverse tcp:8480 tcp:8480
adb reverse tcp:8481 tcp:8481
adb reverse tcp:8482 tcp:8482
```

The current ADB Reverse configuration can be checked with:

```bash
adb reverse --list
```

ADB Reverse settings may be cleared when the device is restarted or the ADB connection is reset.

---

## Known Issues

The following issues may occur with certain client states or databases created by older versions. Reproduction on the latest version is still being investigated.

### Duplicate Area Item Installation

When another item of the same type is purchased while an Area Item is already installed, the existing item may not be replaced correctly, causing the effects of multiple items to be applied simultaneously.

For example, after installing `Studio Microphone` at Edogawa Music, purchasing `Rock Microphone` may leave the appearance of `Studio Microphone` unchanged while applying the effects of both items.

### Live Boost Recovery Calculation

Near the recovery timer boundary or maximum Live Boost capacity, the value displayed by the client may temporarily differ from the value stored by the server.

### Daily Login Bonus State

When using a database created by an older version, the login bonus progression state may reset incorrectly.

### New Data Message When Entering the Area Map

A `New data is available` message may appear when entering the Area Map.

This issue is currently suspected to be related to data from the `Welcome! Joyous New Year!` event.

### Overlapping Character Animations When Entering an Area

An excessive number of character animations may play simultaneously when entering certain areas.

When reporting a bug, including the following information will help with identifying the cause:

* Steps to reproduce
* Server logs
* Related HTTP or WebSocket request paths

---

## License

This project is based on `krdori-local`, which is distributed under the MIT License.

The original copyright notice and MIT License terms are retained. Refer to the `LICENSE` file in this repository for details.

---

## Credits

* Original Project: [RainbowUnicorn7297/krdori-local](https://github.com/RainbowUnicorn7297/krdori-local)
* Special Thanks: **Wuju_puppy**

Thanks to the original developer for making the foundation of this project publicly available, and to all contributors who participated in implementing and testing additional features.
