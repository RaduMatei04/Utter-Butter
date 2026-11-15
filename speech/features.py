"""
features.py: extragerea de trăsături din semnalul vocal.

  - spectrogram(): spectrograma (STFT), calculată explicit cu numpy
                   -> folosită în graficele pentru documentație
  - mfcc():        coeficienții MFCC (13) -> folosiți de metoda MFCC + DTW (pasul 6)
"""

import librosa
import numpy as np

from preprocessing import FRAME_MS, HOP_MS, SAMPLE_RATE, frame_signal, pre_emphasis

N_MFCC = 13   # numărul de coeficienți MFCC păstrați
N_MELS = 40   # numărul de filtre pe scala Mel
N_FFT = 512   # lungimea FFT (≥ 400 eșantioane ale cadrului, putere a lui 2)


def spectrogram(signal, sample_rate=SAMPLE_RATE):
    """Spectrograma = cum se distribuie energia pe frecvențe, în timp.

    Pentru fiecare cadru de 25 ms (pas 10 ms):
      1. înmulțim cu o fereastră Hamming (atenuează marginile cadrului,
         ca tăietura bruscă să nu creeze frecvențe false);
      2. calculăm FFT (transformata Fourier rapidă) -> spectrul cadrului;
      3. păstrăm modulul și îl trecem în decibeli.

    Întoarce (spectru_db, frecvențe_Hz, timpi_s);
    spectru_db are forma (număr_frecvențe, număr_cadre)."""
    frames = frame_signal(signal, sample_rate=sample_rate)
    window = np.hamming(frames.shape[1])          # w[n] = 0.54 - 0.46·cos(2πn/(N-1))
    spectrum = np.fft.rfft(frames * window, n=N_FFT, axis=1)
    magnitude_db = 20 * np.log10(np.abs(spectrum) + 1e-10)

    frequencies = np.fft.rfftfreq(N_FFT, d=1 / sample_rate)    # 0 ... 8000 Hz
    times = np.arange(frames.shape[0]) * HOP_MS / 1000
    return magnitude_db.T, frequencies, times


def mfcc(signal, sample_rate=SAMPLE_RATE, use_pre_emphasis=True):
    """Coeficienții cepstrali pe scala Mel (MFCC).

    Ce face librosa.feature.mfcc, pas cu pas:
      1. împarte semnalul în cadre (25 ms, pas 10 ms) și aplică o fereastră;
      2. FFT -> spectrul de putere al fiecărui cadru;
      3. trece spectrul prin 40 de filtre triunghiulare pe scala Mel
         (scala Mel imită urechea: distinge bine frecvențele joase, mai slab pe cele înalte);
      4. logaritm (urechea percepe intensitatea logaritmic);
      5. DCT (transformata cosinus discretă) -> păstrăm primii 13 coeficienți,
         care descriu forma generală a spectrului (anvelopa = forma tractului vocal).

    Întoarce o matrice (13, număr_cadre)."""
    if use_pre_emphasis:
        signal = pre_emphasis(signal)

    frame_len = int(sample_rate * FRAME_MS / 1000)
    hop = int(sample_rate * HOP_MS / 1000)
    return librosa.feature.mfcc(
        y=signal,
        sr=sample_rate,
        n_mfcc=N_MFCC,
        n_fft=N_FFT,
        win_length=frame_len,
        hop_length=hop,
        window="hamming",
        n_mels=N_MELS,
        center=False,
    )
