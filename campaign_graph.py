"""Traversal of ownership edges, independent of tactical visibility and deployment."""


def iter_objects(galaxy):
    """Yield (object, owning container), rejecting repeated ownership and cycles."""
    seen = set()

    def visit(obj, container):
        if id(obj) in seen:
            raise ValueError(f"Object {obj.id} has multiple containers or a containment cycle")
        seen.add(id(obj))
        yield obj, container
        for unit in getattr(obj, "hidden_units", ()):
            yield from visit(unit, obj)
        for component in (getattr(obj, "hangar_component", None), getattr(obj, "strikecraft_bay_component", None)):
            if component:
                for unit in component.docked_units:
                    yield from visit(unit, component)

    if galaxy:
        for system in galaxy.systems.values():
            for sector in system.hexes.values():
                for obj in (*sector.celestial_bodies, *sector.units, *getattr(sector, "minefields", ())):
                    yield from visit(obj, sector)


def iter_units(galaxy):
    from domain.units import Unit
    for obj, container in iter_objects(galaxy):
        if isinstance(obj, Unit):
            yield obj, container


def find_unit(galaxy, uid):
    if galaxy is None or uid is None:
        return None
    deployed = galaxy.get_unit_by_id(uid)
    if deployed is not None:
        return deployed
    return next((unit for unit, _ in iter_units(galaxy) if unit.id == uid), None)


def is_deployed(unit, galaxy):
    system = getattr(galaxy, "systems", {}).get(unit.in_system)
    sector = system.hexes.get(unit.in_hex) if system else None
    return sector is not None and unit in sector.units


def detach_unit(unit, galaxy):
    for obj, container in list(iter_objects(galaxy)):
        if obj is unit:
            for name in ("units", "hidden_units", "docked_units"):
                collection = getattr(container, name, ())
                if unit in collection:
                    collection.remove(unit)
    for carrier, _ in iter_units(galaxy):
        bay = carrier.strikecraft_bay_component
        if bay:
            if unit in bay.launched_units:
                bay.launched_units.remove(unit)
            if bay.replenishing_unit is unit:
                bay.replenishing_unit = None
                bay.replenish_progress = 0
