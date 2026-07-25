#!/data/data/com.termux/files/usr/bin/bash

if [ -d ./krdori-v2 ]; then
    cd krdori-v2
    git pull https://github.com/NatsuFlatWhite/krdori-v2.git
    source env/bin/activate
elif [ -d ../krdori-v2 ]; then
    git pull https://github.com/NatsuFlatWhite/krdori-v2.git
    source env/bin/activate
else
    yes | pkg upg
    yes | pkg ins git
    yes | pkg ins python
    git clone https://github.com/NatsuFlatWhite/krdori-v2.git
    cd krdori-v2
    python -m venv env
    source env/bin/activate
    python -m pip install --upgrade pip
    python -m pip install websockets
    python -m pip install protobuf
    python -m pip install pycryptodome
    python -m pip install flask
fi
python main.py &
