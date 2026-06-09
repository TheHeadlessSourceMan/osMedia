"""
Beginnings of a tool to stream audio/video of a pulse
stream via WebRTC
"""
import io
import typing
import os
import time
import socket
import threading
import http.server
import socketserver
import subprocess
from typing import List
import numpy as np
import matplotlib.pyplot as plt
from PIL import Image


if os.name=='nt':
    def mkfifo(name:str)->typing.BinaryIO:
        """
        Windows version of mkfifo
        """
        import win32pipe # type: ignore
        import win32file # type: ignore
        pipeName = f'\\\\.\\pipe\\{name}'
        pipe_handle = win32pipe.CreateNamedPipeW(
            pipeName,
            win32pipe.PIPE_ACCESS_OUTBOUND,
            win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_WAIT,
            1, 65536, 65536,
            0, None
        )
        win32pipe.ConnectNamedPipe(pipe_handle, None)
        # Wrap as file-like object
        return win32file._get_osfhandle(pipe_handle) # pylint: disable=protected-access # noqa: E501
else:
    mkfifo=os.mkfifo # pylint: disable=no-member

class WebRTCSampleServer:
    """
    Beginnings of a tool to stream audio/video of a pulse
    stream via WebRTC
    """
    def __init__(self,
        usePublicIP:bool=False,
        alsoPlayAudioLocally:bool=True
        ):
        """ """
        self.usePublicIP:bool=usePublicIP
        self.alsoPlayAudioLocally:bool=alsoPlayAudioLocally
        self.audioSampleRate:int=48000               # Audio sampling rate
        self.graphWidth:int=1000                # Width of the line graph
        self.videoSize:tuple[int,int]=(640,480)
        self.frameRate:int=30
        self._dataBuffer:List[float]=[]
        self._audioBuffer:List[float]=[]
        self.videoPipeName="video_pipe.yuv"
        self.audioPipeName="audio_pipe.pcm"
        # Set up graph
        self._setupMatplotlibGraph()
        # Set up connections
        self.port=self._findEphemeralPort()
        self._setupNamedPipes()
        # Start background threads
        threading.Thread(target=self._graphPlotLoop,daemon=True).start()
        threading.Thread(target=self._writeAudioLoop,daemon=True).start()
        # Start ffmpeg streamer
        self._startWebRTCVideoStream()
        # Optionally play audio locally
        if self.alsoPlayAudioLocally:
            threading.Thread(
                target=self._startWebRTCAudioStream,daemon=True).start()
        # Start HTTP server
        handler=self.HtmlServerHandler
        self.ipAddress="0.0.0.0" if self.usePublicIP else "127.0.0.1"
        with socketserver.TCPServer(
            (self.ipAddress,self.port),handler) as httpd:
            self.host='localhost'
            if self.usePublicIP:
                self.host=socket.gethostbyname(socket.gethostname())
            print(f"Server is running at http://{self.host}:{self.port}")
            httpd.serve_forever()

    def _setupMatplotlibGraph(self):
        """
        Matplotlib Setup (Black Background,Green Line)
        """
        plt.ioff()
        figSize=(self.videoSize[0]/100,self.videoSize[1]/100)
        fig,ax=plt.subplots(figsize=figSize,dpi=100)
        fig.set_facecolor('black')
        ax.set_facecolor('black')
        self._line,=ax.plot([],[],color='lime',linewidth=1)
        ax.set_xlim(0,self.graphWidth)
        ax.set_ylim(-1.5,1.5)
        ax.axis('off')
        self._fig=fig
        self._ax=ax

    def _setupNamedPipes(self)->None:
        """
        Create named pipes (FIFO) for audio and video streams.
        """
        for pipe in [self.videoPipeName,self.audioPipeName]:
            if os.path.exists(pipe):
                os.remove(pipe)
            mkfifo(pipe)

    def addSample(self,rawSampleValue:float)->None:
        """
        Add a new sample point to both audio and visual buffers.
        """
        self._dataBuffer.append(rawSampleValue)
        if len(self._dataBuffer)>self.graphWidth:
            self._dataBuffer.pop(0)
        self._audioBuffer.append(rawSampleValue)
        if len(self._audioBuffer)>self.audioSampleRate*10:
            self._audioBuffer.pop(0)

    def _graphPlotLoop(self)->None:
        """
        Render the matplotlib graph and write raw RGB frames to the video pipe.
        """
        with open(self.videoPipeName,'wb') as pipe:
            while True:
                # rerender graph
                y=np.array(self._dataBuffer[-self.graphWidth:])
                x=np.arange(len(y))
                self._line.set_data(x,y)
                self._ax.set_xlim(max(0,len(y)-self.graphWidth),len(y))
                self._fig.canvas.draw()
                # extract graph as a pil image
                buf=io.BytesIO()
                self._fig.savefig(buf,format="png")
                buf.seek(0)
                img=Image.open(buf).convert("RGB") # Convert to RGB (no alpha)
                img=img.resize(self.videoSize)
                # write it to the pipe
                pipe.write(img.tobytes())
                # wait for next frame
                time.sleep(1/self.frameRate)

    def _writeAudioLoop(self)->None:
        """
        Write 16-bit PCM mono audio data to the audio pipe in chunks.
        """
        with open(self.audioPipeName,'wb') as pipe:
            while True:
                if len(self._audioBuffer)>= 960:
                    chunk=np.array(self._audioBuffer[:960])
                    del self._audioBuffer[:960]
                    samples=(chunk*32767).astype(np.int16)
                    pipe.write(samples.tobytes())
                else:
                    time.sleep(0.01)

    def _startWebRTCVideoStream(self)->None:
        """
        Start FFmpeg as a subprocess to mux and stream WebM over HTTP.
        """
        cmd=[
            "ffmpeg",
            "-f","rawvideo",
            "-pixel_format","rgb24",
            "-video_size",f"{self.videoSize[0]}x{self.videoSize[1]}",
            "-framerate",str(self.frameRate),
            "-i",self.videoPipeName,
            "-f","s16le",
            "-ar",str(self.audioSampleRate),
            "-ac","1",
            "-i",self.audioPipeName,
            "-c:v","libvpx", # VP8 codec
            "-b:v","1M",
            "-c:a","libvorbis",
            "-f","webm",
            self.streamUrl
        ]
        subprocess.Popen(cmd)

    @property
    def streamUrl(self):
        """
        The url of the WebRTC stream
        """
        return f"http://{self.ipAddress}:{self.port}/stream"

    def _startWebRTCAudioStream(self)->None:
        """
        Optionally play raw PCM audio on the local machine using ffplay.
        """
        cmd=[
            "ffplay",
            "-nodisp",
            "-f","s16le",
            "-ar",str(self.audioSampleRate),
            "-ac","1",
            self.audioPipeName
        ]
        subprocess.Popen(cmd)

    class HtmlServerHandler(http.server.SimpleHTTPRequestHandler):
        """
        Custom HTTP request handler that serves
        the HTML viewer and WebM stream.
        """
        def do_GET(self)->None:
            if self.path == "/":
                self.send_response(200)
                self.send_header("Content-Type","text/html")
                self.end_headers()
                server=typing.cast(WebRTCSampleServer,self.server)
                self.wfile.write(server.getPlayerHtml().encode())
            elif self.path == "/stream":
                self.send_response(200)
                self.send_header("Content-Type","video/webm")
                self.send_header("Cache-Control","no-cache")
                self.end_headers()
            else:
                self.send_error(404)

    def getPlayerHtml(self)->str:
        """
        Return HTML with a full-page video element that plays the stream.
        """
        html=r"""
            <!DOCTYPE html>
            <html>
            <head><title>Live Graph Stream</title></head>
            <body style="margin:0;background:black;">
            <video autoplay controls muted style="width:100vw;height:100vh;" src="{streamLocation}"></video>
            </body>
            </html>
            """ # noqa: E501
        streamLocation=self.streamUrl
        return html.replace("{streamLocation}",streamLocation)

    def _findEphemeralPort(self)->int:
        """Bind to an ephemeral port and return its number."""
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as s:
            s.bind(('',0))
            return s.getsockname()[1]


class SimulationExample:
    """
    Simulation example that generates a simple sine wave
    """

    def __init__(self):
        self.server=WebRTCSampleServer()
        threading.Thread(target=self.simulateInputSignal,daemon=True).start()

    def simulateInputSignal(self)->None:
        """
        Feed a sine wave into the system for testing purposes.
        """
        t=0.10
        while True:
            val=np.sin(2*np.pi*2*t)
            self.server.addSample(val)
            t+=1/self.server.audioSampleRate
            time.sleep(1/self.server.audioSampleRate)


def main()->None:
    """
    Main entry point
    start streaming system and servers.
    """
    example=SimulationExample()
    _=example
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
