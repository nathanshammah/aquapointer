import numpy as np
import scipy

from pulser import Pulse, Sequence, Register
from pulser.waveforms import InterpolatedWaveform
import matplotlib.pyplot as plt

import sys
sys.path.append('../aquapointer/')
import utils.detuning_scale_utils as dsu


def default_cost(rescaled_pos, density, variance, bitstring, brad, amp):
    return dsu.ising_energies(rescaled_pos, density, variance, [bitstring], brad, amp)


def gaussian(amp, var, m, x, y):
   """
   Returns the value at point (`x`,`y`) of a sum of isotropic normal
   distributions centered at `mean[0]`, `mean[1]`, ...
   and variance `var`
   """
   return amp*np.exp(-((x-m[0])**2 +(y-m[1])**2)/(2*var))/(2*np.pi*var)


def fit_gaussian(xdata, ydata):
    parameters, _ = scipy.optimize.curve_fit(gaussian, xdata, ydata)
    return parameters[0:2]


def calculate_one_body_qubo_coeffs(density, rescaled_pos, variance, pos):
    gamma_list = dsu.gamma_list(density, rescaled_pos, variance)
    distances_density = dsu.find_possible_distances(rescaled_pos)
    distances_register = dsu.find_possible_distances(pos)
    scale = distances_density[0]/distances_register[0]
    return gamma_list, scale


def scale_detunings(density, pos, rescaled_pos, brad, variance, max_det):
    gamma_list, scale = calculate_one_body_qubo_coeffs(density, rescaled_pos, 
                         variance, pos)
    dets = np.array([item for item in gamma_list])
    for i in range(len(pos)):
    # shift every value by the mean of neighboring detunings
    # a neighbor is defined as atoms within a blockade radius distance
        dets[i] -= np.mean(dsu.neighbouring_gamma_list(density, rescaled_pos, 
            rescaled_pos[i], scale*brad, variance))
    # rescale every detuning such that the maximum detuning is `max_det`
    dets *= max_det/np.max(np.abs(dets))
    return dets


def generate_pulse_sequences(device, register, dets, max_det, pulse_duration, omega):
    """Executes a pulse sequence and returns resulting bitstrings"""
    seq = Sequence(register, device)
    # add an adiabatic pulse for every qubit
    for i in range(len(dets)):
        seq.declare_channel(f'ch{i}', 'rydberg_local')
        seq.target(i, f'ch{i}')
        pulse = Pulse(
            InterpolatedWaveform(pulse_duration, [0, omega, 0]), 
            InterpolatedWaveform(pulse_duration, [-max_det, 0, dets[i]]), 0)
        seq.add(pulse, f'ch{i}')

    return seq


def run_qubo(density, executor, device, register, rescaled_pos, pos, variance, amplitude, brad, pulse_duration, omega, max_det, num_samples):
    dets =  scale_detunings(density, pos, rescaled_pos, brad, variance, max_det)
    pulse_sequence = generate_pulse_sequences(device, register, dets, max_det, pulse_duration, omega)
    samples = executor(pulse_sequence, num_samples)
    solution = best_solution_from_samples(samples, rescaled_pos, density, brad,   
                   variance, amplitude)
    return solution


def best_solution_from_samples(samples, rescaled_pos, density, brad, var, amp, qubo_cost=default_cost):
    best_solutions = []
    samplings = []
    quantum_solutions = sorted(
        samples.items(), key=lambda x: x[1], reverse=True
    )
    quantum_plus_classical_solutions = []
    
    for bitstring, count in quantum_solutions:
        # calculate QUBO cost of bitstring
        cost = qubo_cost(rescaled_pos, density, var, [bitstring], brad, amp)
   # returns empty whenever the blockade constraint is not respected
    try:
        i_bit = cost[0][0]
        i_en = cost[0][1]
        quantum_plus_classical_solutions.append((bitstring, count, i_en))
    
    except IndexError:
       i_bit = bitstring
       i_en = 1e10
       quantum_plus_classical_solutions.append((bitstring, count, i_en))
    
    best_solution = sorted(quantum_plus_classical_solutions, key=lambda x: x[2], reverse=False)[0][0]
    best_solutions.append(best_solution)
    samplings.append(np.array(quantum_plus_classical_solutions, dtype=object))
    return samplings