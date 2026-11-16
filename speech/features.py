"""
features.py: trăsături extrase din semnal.

  spectrogram()  cum se distribuie energia pe frecvențe, în timp (pentru grafice)
  mfcc()         13 coeficienți MFCC la fiecare 10 ms (pentru metoda DTW)
"""

import librosa
import numpy as np

from preprocessing import FRAME, HOP, SAMPLE_RATE, pre_emphasis, split_into_frames

N_FFT = 512   # lungimea FFT (putere a lui 2, mai mare decât cadrul de 400)


def spectrogram(signal):
    """Pentru fiecare cadru: fereastră Hamming -> FFT -> modul în dB.
    Întoarce (spectru_dB, frecvențe_Hz, timpi_s)."""
    frames = split_into_frames(signal) * np.hamming(FRAME)   # fereastra atenuează marginile cadrului
    spectrum = np.abs(np.fft.rfft(frames, n=N_FFT))
    spectrum_db = 20 * np.log10(spectrum + 1e-10)

    frequencies = np.fft.rfftfreq(N_FFT, 1 / SAMPLE_RATE)    # 0 ... 8000 Hz
    times = np.arange(len(frames)) * HOP / SAMPLE_RATE
    return spectrum_db.T, frequencies, times


def mfcc(signal):
    """MFCC = Mel-Frequency Cepstral Coefficients. Pașii făcuți de librosa:
      1. cadre de 25 ms + fereastră Hamming
      2. FFT -> spectrul de putere
      3. 40 de filtre pe scala Mel (imită urechea: precisă la frecvențe joase)
      4. logaritm
      5. DCT -> păstrăm primii 13 coeficienți (forma tractului vocal)
    Întoarce o matrice (13, număr_cadre)."""
    return librosa.feature.mfcc(
        y=pre_emphasis(signal), sr=SAMPLE_RATE, n_mfcc=13, n_mels=40,
        n_fft=N_FFT, win_length=FRAME, hop_length=HOP, window="hamming", center=False,
    )
