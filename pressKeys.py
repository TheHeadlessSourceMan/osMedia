"""
Press keyboard keys
"""
import typing
import time
import ctypes


# Map virtual key codes for media keys
VK_MEDIA_NEXT_TRACK=0xB0
VK_MEDIA_PREV_TRACK=0xB1
VK_MEDIA_STOP=0xB2
VK_MEDIA_PLAY_PAUSE=0xB3
VK_VOLUME_MUTE=0xAD
VK_VOLUME_DOWN=0xAE
VK_VOLUME_UP=0xAF
WindowsVkKeyCodes:typing.Dict[str,int]={
    "PLAY":VK_MEDIA_PLAY_PAUSE,
    "PAUSE":VK_MEDIA_PLAY_PAUSE,
    "PLAY_PAUSE":VK_MEDIA_PLAY_PAUSE,
    "STOP":VK_MEDIA_STOP,
    "VOL_UP":VK_VOLUME_UP,
    "VOLUME_UP":VK_VOLUME_UP,
    "VOL_DOWN":VK_VOLUME_DOWN,
    "VOLUME_DOWN":VK_VOLUME_DOWN,
    "MUTE":VK_VOLUME_MUTE,
    "VOL_MUTE":VK_VOLUME_MUTE,
    "VOLUME_MUTE":VK_VOLUME_MUTE,
    "SKIP":VK_MEDIA_NEXT_TRACK,
    "NEXT":VK_MEDIA_NEXT_TRACK,
    "PREVIOUS":VK_MEDIA_PREV_TRACK,
    "PREV":VK_MEDIA_PREV_TRACK,
    "SKIP_TRACK":VK_MEDIA_NEXT_TRACK,
    "NEXT_TRACK":VK_MEDIA_NEXT_TRACK,
    "PREVIOUS_TRACK":VK_MEDIA_PREV_TRACK,
    "PREV_TRACK":VK_MEDIA_PREV_TRACK,
}


# C struct definitions for SendInput API
PUL=ctypes.POINTER(ctypes.c_ulong)


class KEYBDINPUT(ctypes.Structure):
    """
    Windows KEYBDINPUT struct
    """
    _fields_=[
        ("wVk",ctypes.c_ushort),
        ("wScan",ctypes.c_ushort),
        ("dwFlags",ctypes.c_ulong),
        ("time",ctypes.c_ulong),
        ("dwExtraInfo",PUL)]


class INPUT(ctypes.Structure):
    """
    Windows INPUT struct
    """
    class _INPUT(ctypes.Union):
        _fields_=[("ki",KEYBDINPUT)]
    _anonymous_=("_input",)
    _fields_=[("type",ctypes.c_ulong),("_input",_INPUT)]


def asKeyCode(keyCode:typing.Union[int,str])->int:
    """
    Convert a single shorthand to os key code
    """
    if isinstance(keyCode,int):
        return keyCode
    if len(keyCode)==1:
        # regular key
        encoded=ord(keyCode.encode('utf-16'))
        return ctypes.windll.User32.VkKeyScanW(encoded)
    # special key
    keyCode=keyCode.replace('[','').replace(']','').strip()\
        .replace(' ','_').replace('VK_','')
    modifierList=keyCode.split('+')
    ret=0
    for kc in modifierList:
        if len(kc)==0:
            ret|=asKeyCode('+')
        elif len(kc)<2:
            ret|=asKeyCode(kc)
        else:
            kc=keyCode.upper()
            kcVal=WindowsVkKeyCodes.get(kc)
            if kcVal is None:
                raise EncodingWarning(
                    f'Unable to translate "{kc}" to keystrokes')
            ret|=kcVal
    return ret

def pressKey(keyCode:typing.Union[int,str])->None:
    """
    Press one single keyboard key

    Supports:
        A single char text key "s"
        key names (with/without []) "PAGE_UP"
        meta keys "CTRL+C"

    NOTE: if you want more complicated sequences, you may
    want to try pressKeys() instead.
    """
    original=keyCode
    keyCode=asKeyCode(keyCode)
    if keyCode==0:
        raise EncodingWarning(
            f'Unable to translate "{original}" to keystrokes')
    extra=ctypes.c_ulong(0)
    ii_=INPUT._INPUT() # pylint: disable=protected-access
    ii_.ki=KEYBDINPUT(keyCode,0,0,0,ctypes.pointer(extra)) # pylint: disable=attribute-defined-outside-init # noqa: E501
    x=INPUT(ctypes.c_ulong(1),ii_)
    # Key down
    ctypes.windll.user32.SendInput(1,ctypes.pointer(x),ctypes.sizeof(x))
    # Key up
    ii_.ki=KEYBDINPUT(keyCode,0,2,0,ctypes.pointer(extra)) # pylint: disable=attribute-defined-outside-init # noqa: E501
    x=INPUT(ctypes.c_ulong(1),ii_)
    ctypes.windll.user32.SendInput(1,ctypes.pointer(x),ctypes.sizeof(x))


def pressKeys(keyStream:str,timeDelaySec:float=0.05)->None:
    r"""
    Press a series of keys.

    Supports:
        Normal letters
        special keys "[UP_ARROW]"
        meta keys "[CTRL+C]"
        and "[" key via "\["
    """
    nextCharEscaped=False
    buildingSpecial:typing.List[str]=[]
    for c in keyStream:
        if buildingSpecial:
            buildingSpecial.append(c)
            if c==']':
                pressKey(''.join(buildingSpecial))
                if timeDelaySec>0:
                    time.sleep(timeDelaySec)
                buildingSpecial=[]
        else:
            if nextCharEscaped:
                pressKey(c)
                if timeDelaySec>0:
                    time.sleep(timeDelaySec)
                nextCharEscaped=False
            elif c=='\\':
                nextCharEscaped=True
            elif c=='[':
                buildingSpecial.append(c)
            else:
                pressKey(c)
                if timeDelaySec>0:
                    time.sleep(timeDelaySec)


def main(args:typing.Iterable[str])->int:
    """
    Run like from the command line.

    Does not expect args[0] to be program name.
    """
    printHelp=False
    if not args:
        printHelp=True
    else:
        for arg in args:
            if arg in ('-h','--help'):
                printHelp=True
            pressKeys(arg)
    if printHelp:
        print('USAGE:')
        print('   pressKey [keys]')
        print('EXAMPLE:')
        print('   pressKeys [CTRL+C] hello [PLAY] [VOLUME_UP]')
        return -1
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[1:]))
