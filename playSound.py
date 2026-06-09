"""
play a sound file
"""
import typing
import os
from pathlib import Path
try:
    import winsound

    def playSound(filename:typing.Union[str,Path]):
        """
        play a sound file
        """
        winsound.PlaySound(str(filename),winsound.SND_FILENAME)
except ImportError:
    def playSound(filename:typing.Union[str,Path]):
        """
        play a sound file
        """
        _=filename
        raise NotImplementedError(f'Not implemented on {os.name}')
