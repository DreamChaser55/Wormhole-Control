"""Advisory population costs for disclosed colonies; never command restrictions."""
import math


def colonist_load_advice(body, maximum_amount):
    population = max(0.0, float(body.population))
    capacity = max(0.0, float(body.max_population))
    growth = max(0.0, float(getattr(body, 'population_growth_rate', 0)))
    # Keep a useful seed on a young colony and at least half a mature donor.
    retained = min(population, capacity, max(min(10.0, capacity / 4), population / 2))
    maximum = max(0, math.floor(min(population, maximum_amount)))
    residual = population - maximum
    recovery = (0 if maximum == 0 else None if residual <= 0 or growth <= 0 else
                math.ceil((math.log(population) - math.log(residual)) / math.log1p(growth)))
    return {'current_population': population,
            'recommended_amount': max(0, math.floor(min(maximum_amount, population - retained))),
            'recommended_retained_population': round(retained, 4),
            'growth_rate_per_round': growth,
            'hypothetical_next_maximum_load': {
                'hypothetical_load_amount': maximum,
                'population_after_load': round(residual, 4),
                'recovery_rounds_to_current_population': recovery,
            }}
