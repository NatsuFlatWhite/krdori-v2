"""Kakao session server"""

import asyncio
import base64
import json
import logging
import re
import time
import zlib

try:
    from websockets.asyncio.server import serve
except ImportError:
    try:
        from websockets.server import serve
    except ImportError:
        from websockets import serve
from websockets.exceptions import ConnectionClosed

logging.basicConfig(format='%(message)s', level=logging.DEBUG)


async def handler(websocket):
    prereq = re.search('prereq=(.*)', websocket.request.path).group(1)
    prereq = base64.urlsafe_b64decode(prereq)
    prereq = zlib.decompress(prereq)
    prereq = json.loads(prereq)
    requestUri = prereq[0]
    header = json.dumps(
        {
            'txNo': prereq[1]['txNo']
        },
        separators=(',', ':')
    )
    body = json.dumps(
        {
            'status': 200,
            'desc': 'success',
            'content': {
                'player': {
                    'playerId': '900000000000',
                },
                'zat': 'zat',
                'zatExpiryTime': int(time.time()*1000) + 86_400_000,
            }
        },
        separators=(',', ':')
    )
    await websocket.send(f'["{requestUri}",{header},{body}]')
    
    try:
        async for message in websocket:
            print(message, flush=True)

            try:
                request = json.loads(message)
                request_uri = request[0]
                if len(request) < 3:
                    await websocket.send(message)
                    continue

                tx_no = request[1].get('txNo', 0)
                res_header = json.dumps({'txNo': tx_no}, separators=(',', ':'))

                if request_uri == 'service/v3/log/writeSdkBasicLog':
                    res_body = json.dumps({'status': 200, 'desc': 'success', 'content': {}}, separators=(',', ':'))
                    await websocket.send(f'["{request_uri}",{res_header},{res_body}]')
                elif request_uri == 'v2/user/me':
                    res_body = json.dumps(
                        {
                            'status': 200,
                            'desc': 'success',
                            'content': {
                                'id': 1000000000,
                                'connected_at': '2000-01-01T00:00:00Z',
                                'has_signed_up': True,
                                'properties': {'nickname': 'KRdori'},
                                'kakao_account': {
                                    'profile': {'nickname': 'KRdori'},
                                    'service_user_id': 100000000000000000,
                                },
                            },
                        },
                        separators=(',', ':'),
                    )
                    await websocket.send(f'["{request_uri}",{res_header},{res_body}]')
                else:
                    await websocket.send(message)
            except Exception as e:
                print(f"Error handling message: {e}", flush=True)
                await websocket.send(message)

    except ConnectionClosed:
        pass


async def main(port):
    async with serve(
        handler,
        '',
        port,
        ssl=None,
        compression=None,
    ):
        print(f'Running session server on port {port}...')
        await asyncio.get_running_loop().create_future()


if __name__ == '__main__':
    asyncio.run(main(8481))
