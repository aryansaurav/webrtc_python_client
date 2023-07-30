# webrtc_server.py to work with Unity Renderstreaming broadcast sample

import asyncio
import cv2
import numpy as np
from aiortc import RTCIceCandidate, RTCPeerConnection, RTCSessionDescription, VideoStreamTrack, RTCConfiguration, RTCIceServer
from aiortc.contrib.media import MediaBlackhole, MediaPlayer, MediaRecorder
from av import VideoFrame
from websockets import connect
import json
import uuid
import re
import logging
logging.basicConfig(level=logging.DEBUG)


uri = 'ws://34.89.23.156:8805'
# uri = 'ws://127.0.0.1'
CONNECTION_ID = 'python_client0'
recording_file = 'aiortc_recorded.mp4'
pc_init = False
pc0_init = False


configuration = RTCConfiguration(
    iceServers=[
        RTCIceServer(urls='stun:stun.l.google.com:19302'),
		RTCIceServer(urls='stun:stun1.l.google.com:19302'),
        RTCIceServer(urls='stun:stun2.l.google.com:19302'),
        RTCIceServer(urls='stun:stun3.l.google.com:19302'),
        RTCIceServer(urls='stun:stun4.l.google.com:19302'),

        # RTCIceServer(
        #     urls='turn:t.y-not.app:443',
        #     username='user',
        #     credential='pass'
        # )
    ]
)


def parse_ice_candidate(candidate, sdpMid, sdpMLineIndex):
    m = re.match(r'candidate:(\S+) (\d) (\S+) (\d+) (\S+) (\d+) typ (\S+)', candidate)
    if not m:
        raise ValueError('Invalid candidate')
    return RTCIceCandidate(
        foundation=m.group(1),
        component=m.group(2),
        protocol=m.group(3),
        priority=int(m.group(4)),
        ip=m.group(5),
        port=int(m.group(6)),
        type=m.group(7),
        sdpMid=sdpMid,
        sdpMLineIndex=sdpMLineIndex
    )

class VideoImageTrack(VideoStreamTrack):
    """
    A video track that returns an image.
    """
    def __init__(self, video_frame):
        super().__init__()  # don't forget this!
        self.img = video_frame

    async def recv(self):
        return self.img

async def consume_signaling(pc,pc0, recorder):
    pc.createDataChannel('chat')  # Create a data channel named 'chat'
    global pc_init, pc0_init
    
    async with connect(uri) as ws:

        # send offer
        offer = await pc0.createOffer()
        await pc0.setLocalDescription(offer)
        # Convert the offer to JSON before sending
        offer_dict = {
            "sdp": offer.sdp, 
            "type": "offer", 
            "connectionId": CONNECTION_ID, 
            "data": {
                "sdp": offer.sdp, 
                "type": "offer",
                "connectionId": CONNECTION_ID,
                "polite": True

                }
        }
        offer_json = json.dumps(offer_dict)
        await ws.send(offer_json)

        # wait for answer
        # answer_json = await ws.recv()
        # answer_dict = json.loads(answer_json)
        # print('answer received: ', answer_dict)
        # # Parse the answer from JSON back to an RTCSessionDescription
        # answer = RTCSessionDescription(sdp=answer_dict['data']["sdp"], type=answer_dict["type"])
        # await pc.setRemoteDescription(answer)
        # print('answer set successfully')

        # wait for end of signaling
        async for message in ws:
            msg_dict = json.loads(message)
            # Parse the answer from JSON back to an RTCSessionDescription
            if msg_dict['type']=='answer' and pc0_init==False:
                print('answer received from: ', msg_dict['from'])

                answer = RTCSessionDescription(sdp=msg_dict['data']["sdp"], type=msg_dict["type"])
                await pc0.setRemoteDescription(answer)

                print('answer set successfully')
                answer_dict = {
                    "type": "answer",
                    "data": {
                        "connectionId": CONNECTION_ID,  # Added: include the connectionId in the message
                        "sdp": pc0.localDescription.sdp,
                        "type": "answer",
                        "polite": True
                    }
                }
                pc0_init = True
                # await ws.send(json.dumps(answer_dict))

            if msg_dict['type']=='offer' and  msg_dict['from']==CONNECTION_ID and pc_init==False:
                print('offer received from: ', msg_dict['from'])

                offer_received = RTCSessionDescription(sdp=msg_dict['data']["sdp"], type=msg_dict["type"])
                await pc.setRemoteDescription(offer_received)
                print('offer set successfully')
                await recorder.start()

                answer_remote = await pc.createAnswer()
                await pc.setLocalDescription(answer_remote)

                answer_dict = {
                    "type": "answer",
                    "data": {
                        "connectionId": CONNECTION_ID,  # Added: include the connectionId in the message
                        "sdp": pc.localDescription.sdp,
                        "type": "answer",
                        "polite": True
                    }
                }
                answer_json = json.dumps(answer_dict)
                await ws.send(answer_json)
                pc_init = True
            if msg_dict["type"] == "candidate" and msg_dict["from"] == CONNECTION_ID:
                    candidate = parse_ice_candidate(
                        msg_dict['data']['candidate'],
                        msg_dict['data']['sdpMid'],
                        msg_dict['data']['sdpMLineIndex']
                        )
                    await pc.addIceCandidate(candidate)
                    print("adding candidate")


                # offer_dict = {
                #     "type": "offer",
                #     "data": {
                #         "connectionId": CONNECTION_ID,  # Added: include the connectionId in the message
                #         "sdp": pc.localDescription.sdp,
                #         "type": "offer",
                #         "polite": False
                #     }
                # }
                # await ws.send(answer_msg_json)




def create_frame(image):
    """
    Create a video frame from an image
    """
    frame = VideoFrame.from_ndarray(image, format="bgr24")
    return frame

async def run(pc, pc0, player, recorder):
    @pc.on("track")
    async def on_track(track):
        print("Track %s received" % track.kind)

        if track.kind == "video":
            # local_video = VideoImageTrack(create_frame(np.zeros((100, 100, 3), dtype=np.uint8)))
            # pc.addTrack(local_video)
            # recorder.addTrack(local_video)

            # print('added video track')

            while True:
                print("receiving frame ..")
                print("pc connection state:", pc.connectionState)  

                frame = await track.recv()
                img = frame.to_ndarray(format="bgr24")
                print("received frame ")
                cv2.imshow('OpenCV', img)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break



        @track.on("ended")
        async def on_ended():
            # stop displaying video
            cv2.destroyAllWindows()

    await consume_signaling(pc, pc0, recorder)

    await recorder.stop()
    await player.stop()

if __name__ == "__main__":
    pc = RTCPeerConnection(configuration)
    pc0 = RTCPeerConnection(configuration) # For initial offer
    pc0.createDataChannel('data')
    recorder = MediaRecorder(recording_file)
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(
            run(pc, pc0, None, recorder))
    except Exception as e:
        print(e)
    finally:
        loop.run_until_complete(recorder.stop())

        # loop.run_until_complete(pc.close())
