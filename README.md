# Inductive Appliance Fingerprinter
 
**In one-line:** Classifying electrical appliances from their current waveform. 
 
**Status:** Stage 1 complete and measurements validated. Stage 2 in progress.
 
**Stage 1:** non-intrusive CT-based current sensing on an ESP32-S3.
 
**Stage 2:** reducing noise, converting data to waveform graphs
 
**Stage 3:** sampling in stacks and labelling the events to train home systems to identify appliances.
 
<img width="820" height="627" alt="Screenshot 2026-08-24 at 6 18 24 PM" src="https://github.com/user-attachments/assets/604869b9-8c4c-4be2-9254-c9c67c4d7755" />

_Image of Appliance-Fingerprinter_
 
## Why
Appliances have distinguishable current signatures because their internals determine when in the cycle they draw current. For example, a lightbulb/toaster's resistive load is different to a blender motor's initial spike in current draw to spin up the blades. To achieve an intelligent smart home system, we would use AI to "guess" at what appliances are plugged in and are being used at certain times. That way, humans do not need to tell apps what is plugged in where, but rather the home itself will know. Additionally, the current signature can provide an insight into the health of the appliances over time - which could provide early warnings to users of appliance faults.
 
## Why I wanted to build it
The reasons I decided to build it are 3 fold.
1. I recently read The Player of Games by Iain M. Banks and I was fascinated by the Minds (General Intelligence AI that manages Orbitals, which are spinning space habitats). They are Always-On General Intelligence systems that allocate power, information and services around the Orbitals. I decided that in commercial applications, where machine vision would not be possible, a system similar to mine would have to be used for a "Mind" to have full knowledge of all the electronics in a factory, stadium or hotel for example. 
2. As Class 4 power has recently been unbanned in residential applications, I was mulling over building a power infrastructure start up that would use fault managed power and AI to manage consumption at appliance level, as well as allow a completely off the grid neighborhood solar sharing scheme. This project felt like a simple and focused version of what an MVP would look like for that rather ambitious operation.
3. I knew going into the project that although measuring appliance's current signatures is rather lame, the exact same technology is used by satellite communications and electronic-warfare systems which are two areas that are not lame in the slightest. I learnt as much as I could about the signal processing and sampling rates during the process.

## How it works
The signal chain and components:
 
1. The clamp picks up the electromagnetic field and sends a current to the circuit
2. The current passes through a burden (220Ω resistor) which creates a voltage that the ADC can read on the ESP32
3. Two 10kΩ resistors in series range-frame the voltage that is oscillating between negative and positive. They halve the 3.3V, creating a reference voltage. One side of the burden resistor is connected to that reference supply resulting in the ADC reading being 1.65V +/- the burden (the ADC can only read positive values from 0-3.3V for voltage in the ESP32S3).
4. The 10µF capacitor gives the 50Hz signal a low impedance route to ground. The 100nF capacitor filters out the extremely high frequencies coming from the ESP32 itself. This prevents those signals from interfering with the reference voltage created at the 10kΩ resistors.

<img width="835" height="528" alt="image" src="https://github.com/user-attachments/assets/9caa0320-f47c-4159-854a-faab566b3433" />

_Image of labelled circuit. The sleeve and tip jumpers go to the 3.5mm breakout board for the audio jack from the clamp. The 3.3V, GPIO 4 and GND jumpers go to the ESP32._
 
## The Physics:
**1. Ampère's Law:** Around any current carrying conducting wire is a magnetic field of magnitude given by B = μ₀I/2πr. Ampère's circuital law states "the line integral of a magnetic field around a closed loop is equal to the permeability of free space multiplied by the net electric current enclosed by the loop." As a result, the clamp reads the same if the wire is on the side of the clamp vs in the middle (in air), so a loose fit doesn't make a difference. Also, a normal mains cable carries equal and opposite currents in the same cable which would cancel each other out in the reading from the clamp. Therefore I built a splitter, so I would be able to clamp only one part of the mains cable. The cautiously crafted splitter can be seen below. I tested it extensively on a multimeter before plugging it into mains to make 100% sure everything was right.
 
<img width="823" height="614" alt="Screenshot 2026-08-24 at 6 19 15 PM" src="https://github.com/user-attachments/assets/d51799ec-5fa1-489f-9d42-51fd2018ddc4" />

_Image of splitter_

**2. Faraday's Law:** The clamp I am using is called a SCT-013. Its main winding is the mains wire itself which passes through a split ring of ferrite. Ferrite's extremely high permeability concentrates the flux so that almost all of it is conducted by the secondary, 2000 turn, coil. As a result of ferrite being significantly more permeable than air, any small air gaps or dust in the split ferrite ring will destroy the sensitivity of the system. Faraday's law gives the induced EMF as ε = −N(dΦ/dt), and the resulting secondary current is the primary current divided by the turns ratio: 100A through the conductor produces 50mA from the clamp. This depends on change in flux so the sensor is blind to DC - one of the limitations of the system.
 
## Linearity and Sampling:
Fingerprinting an appliance depends on the waveform shape. For this reason, the system must only perform linear operations on the signal to preserve the shape and allow it to be readable by the ADC. Ferrite permeability is effectively constant before saturation, Faraday's law is linear and Ohm's law at the current to voltage conversion is linear, so the waveform shape is preserved. Keeping the harmonic ratios constant while scaling them is critical for accuracy. The second precaution I had to take was to do with sampling. The Nyquist theorem says when sampling and converting analogue to digital data, you should sample at a frequency at least 2x higher than the highest frequency component present in the signal. This avoids higher frequencies folding over and showing up as "ghost" lower frequencies. At a 10kHz sampling rate, my Nyquist limit is 5kHz. The highest frequency I care about is the 40th harmonic of 50Hz at 2kHz, so I have around 2.5× the margin I strictly need.

## Why this architecture matters beyond my Nutribullet
Fundamentally, this project is structurally identical to a software-defined radio receiver. The CT clamp converts a magnetic field to current (which would be an antenna), the burden and bias nodes are analog signal conditioning, the RMS calculation is DSP. This is a slight stretch, but the differences from a satellite downlink are only really quantitative. The satellite transmits at GHz frequencies, so the receiver mixes it down to a workable intermediate frequency before sampling — otherwise you'd need an ADC running at hundreds of megasamples per second so that you obey the Nyquist Theorem.

The precautions to take are also quite similar. Dynamic range: the inrush from the Nutribullet clipped because of my 220Ω burden choice. Noise floor: my fingerprinter is not able to measure anything below 0.2A which is a (very very simple version of) link budget calculation. Additionally, aliasing, quantisation and testing your instrument's transfer function all transfer directly to SATCOM applications.

Once I add a voltage channel, computing reactive power means correlating current against the voltage reference and against a copy shifted 90°. That's the same operation as IQ sampling in a satellite receiver: correlate against a reference and its quadrature copy, recover amplitude and phase.

<img width="220" height="244" alt="Screenshot 2026-08-25 at 1 01 31 PM" src="https://github.com/user-attachments/assets/8da65d54-b070-4f2e-942b-3d1a8db49f7f" />

_L3HARRIS Link Budget Calculator Software (only very very slightly more complex than mine)_


## Component choices
**The 220Ω resistor**

R = (1.65 × 2000) / (13 × 1.414) ≈ 180Ω
 
I used 220Ω, which trades range for sensitivity: the ceiling drops to 10.6A (~2.4kW) but each amp produces 22% more signal. Given that the noise floor rather than the ceiling is the binding constraint for most appliances, this is the right side of the trade — though it is the direct cause of the clipped inrush noted in Results.
 
**The two 10kΩ resistors**
 
Two equal resistors in series across the 3.3V rail produce exactly half the supply at their junction. Equal values are required because the ADC's range is symmetric about its midpoint; any other ratio wastes headroom on one side.
 
**Why 10µF and 100nF ceramic**

To an AC signal, the two 10kΩ resistors appear in parallel. The clamp pushes roughly 0.8mA of signal current into and out of that node, which by Ohm's law displaces it by about 4mV. For the ADC it is a 2% error that correlates with the signal and therefore distorts waveform shape.
 
Capacitive reactance X_C = 1/2πfC gives the 10µF capacitor an impedance of ~318Ω at 50Hz, sixteen times lower than the resistors. The signal current takes that path instead, and the node displacement falls to ~0.24mV. At DC the capacitor is an open circuit, so the divider sets the reference undisturbed. The 100nF ceramic serves the same purpose at much higher frequencies which handles switching noise from the ESP32's own digital circuitry.
 
The two resistors are in series as a DC path, but from the midpoint's perspective both lead to a rigid rail, so to a signal they appear in parallel — hence 5kΩ rather than 20kΩ.
 
## Demo Video
 
Measured on a Nutribullet blender 1200W, 220Ω burden, ~10 kS/s sampling.
 
<video src="https://github.com/user-attachments/assets/21b7057b-2ef2-4654-bc27-a4308dca15d9" width="320" controls></video>
 
### Results — Nutribullet blender (universal motor)

| Phase | RMS current | Crest factor | What it shows |
|---|---|---|---|
| Idle | 0.17 – 0.22 A | — | Noise floor. Sets the detection limit. |
| Inrush | 3.73 A | **4.3** | Stalled rotor, no back-EMF to limit current. |
| Decay (~1 s) | 1.66 A | 2.9 | Motor spinning up, back-EMF rising. |
| Steady state | 1.45 – 1.71 A | ~3.2 | Running. Brush commutation keeps it spiky. |

**Notes**
1. Crest factor is the fingerprint: The blender reaches 4.3 at inrush, which means current arrives in sharp bursts rather than smoothly. That one number separates a motor from a heating element without any classifier. 
2. The inrush clipped (a design consequence): The transient drove the ADC to both rails (`0` and `4095`), so 3.73 A is a floor, not the true peak. This follows directly from the 220Ω burden, which caps measurement at 10.6 A. A 100Ω burden would capture it at the cost of halving sensitivity to small loads.
3. The bias network held: Mean stayed at ~1879 counts through every state including the clipped transient, confirming the reference doesn't shift under load.
4. <a id="note4"></a>`peak` is the maximum deviation within a 200 ms window, not a true per-cycle peak, so crest factors are indicative rather than precise. [See Limitation 8.](#lim8)

### <a id="point4"></a>Point 4 is important
_so I shall take the liberty of expanding._
Currently, the peak reading is the maximum deviation within the 200 ms window, but each cycle is around 20 ms, which is determined by the AC frequency, which is 50 Hz. Both the peak and the RMS are calculated over the entire 200 ms window. As seen in the diagram I drew, the first wave is perfectly sinusoidal, but towards the tail, the amplitude decreases. The second wave, or third from the top, is also perfectly sinusoidal and has the same peak value as the first wave, but the amplitude is constant over the entire 200ms window. They are both completely sinusoidal waves, so in theory they should have the exact same crest factor, but because I am calculating the RMS and the peak over the entire window, the RMS of the first wave is pulled down by the decaying tail, while the peak stays the same, so the crest factor comes out higher. The crest factor uses the RMS and the peak to calculate a value which should give an insight into the shape of the signal.

<img width="291" height="400" alt="Screenshot 2026-08-25 at 2 04 42 PM" src="https://github.com/user-attachments/assets/ea6f2541-fc5b-45a9-a496-8a5faf2b2b3f" />

Using the blender motor as an example, the RMS would be pulled down relative to the peak by the decay after the motor spins up, and the peak would be found somewhere in that inrush event. However, because of the brush commutation of the motor, it is likely that the signal will be very spiky. Because of the fact that the peak is calculated over the entire window, that information is lost. That said, you can only turn a blender on when it's plugged in, so the system should always be able to detect an initial surge and classify the appliance as one with a motor, but it still cannot differentiate between different types of motors. The way to fix this would be to calculate the RMS and the peak over every single cycle. That said, this only matters in stage 1, because from stage 2 I should also have a waveform graph.
 
## Limitations
1. No voltage channel: Cannot compute real power. Everything reported is apparent power at an assumed voltage based on UK mains supply (230V).
2. Noise floor ~0.2 A: Loads below roughly 50 W are indistinguishable from noise. Most chargers and standby loads are invisible.
3. Clipping above ~10.6 A: Motor inrush and high-power resistive loads saturate.
4. ADC non-linearity: Repeatability is acceptable, which is sufficient for classification but not for metering.
5. No anti-alias filter: Content above 5 kHz folds into the measurement band. Mitigated somewhat by the CT's own roll-off.
6. Readings are unverified against a reference. Only differential measurements can be trusted.
7. Non-coherent sampling: The window is not an exact integer number of cycles.
8. <a id="lim8"></a>Calculations of RMS and Peak values over a window instead of cycle by cycle. [See expanded note above.](#point4)

_I plan to resolve 2, 3, 7 and 8 in stage 2. Item 5 is a judgement call - an anti-alias filter is cheap, but some information would be lost like the brush commutation in appliances with motors which is an important data point for classification._
 
## Safety Note
While I created the mains supply splitter, I tested everything extensively with a multimeter before plugging it into the mains supply. There are no open areas to the mains supply to touch on this design. In the tiny case someone might decide to build something similar based on this repo, I would suggest being extremely cautious when dealing with mains power.

## Use of AI in this project

I used Claude for the circuit topology, component values, the Arduino sketches, and a lot of physics questions. I built and tested the splitter, wired and debugged the circuit, ran the experiments, and interpreted the results. The debugging was mine: the 790Ω divider reading that turned out to be the ESP32's power supply, the dead jumper that made the clamp look broken and the crest factor limitation in Point 4, which came from constructing a counter-example and checking it.
