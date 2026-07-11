"""
Light-weight ffmpeg wrapper that records and stores footage locally.
"""
import subprocess
from pathlib import Path

class VideoRecorder:
    def __init__(self, source: str, destination: str | Path = "footage") -> None:
        """
        Records video using FFMPEG and stores it locally.

        Usage (typical):
            recorder = VideoRecorder(source="rtsp://...", destination="footage")
            recorder.start() # ffmpeg is now running in the background

            ...
            do other things here concurrently
            ...

            recorder.stop()

        Usage (context manager):
            with VideoRecorder(source="rtsp://...") as recorder:
                ...
                do other things here concurrently
                ...
        """
        
        self._destination = Path(destination)
        self._destination.mkdir(parents=True, exist_ok=True)

        self._source = source
        self._process: subprocess.Popen | None = None
        self._cmd = [
            'ffmpeg',
            '-rtsp_transport', 'tcp',
            '-i', self._source,
            '-c', 'copy',
            '-f', 'segment',
            '-segment_time', '60',
            '-reset_timestamps', '1',
            '-strftime', '1',
            str(self._destination / 'cam_%Y-%m-%d_%H-%M-%S.mkv'),
        ]

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._process is not None:
            raise RuntimeError("VideoRecorder is already running.")
        self._process = subprocess.Popen(self._cmd, stdin=subprocess.PIPE)

    def stop(self) -> None:
        if self._process is None:
            return
        
        try:
            self._process.communicate(input=b"q", timeout=5)
        except subprocess.TimeoutExpired:
            self._process.terminate()
            self._process.wait()
        finally:
            self._process = None
    

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "VideoRecorder":
        """Start the recorder and return self for use in a ``with`` block."""
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        """Stop the recorder on exit"""
        self.stop()