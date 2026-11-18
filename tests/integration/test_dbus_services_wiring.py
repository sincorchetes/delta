"""Every service the configuration builds must reach the D-Bus object, at startup and on reconfigure.

A service added to `Services` but left out of the startup call answered «not available» only in the
real daemon, where nothing caught it: «Restore deleted…» did exactly that.
"""

import dataclasses

from delta.daemon.composition import Services
from delta.daemon.service import DeltaService


def sentinels():
    return Services(**{field.name: object() for field in dataclasses.fields(Services)})


def test_starting_from_the_built_services_wires_every_one_of_them(bus):
    built = sentinels()

    service = DeltaService.from_services(bus, built)
    try:
        for field in dataclasses.fields(Services):
            assert getattr(service, f"_{field.name}") is getattr(built, field.name), field.name
    finally:
        service.unregister()


def test_reconfiguring_swaps_every_one_of_them(bus):
    service = DeltaService.from_services(bus, sentinels())
    later = sentinels()
    try:
        service.reconfigure(later)
        for field in dataclasses.fields(Services):
            assert getattr(service, f"_{field.name}") is getattr(later, field.name), field.name
    finally:
        service.unregister()


def test_the_extras_that_are_not_configuration_are_passed_through(bus):
    jobs = object()
    service = DeltaService.from_services(bus, sentinels(), jobs=jobs)
    try:
        assert service._jobs is jobs
    finally:
        service.unregister()


def test_every_field_of_services_is_a_constructor_argument_of_the_service():
    """The whole point of `from_services`: no field can be left without a place to go."""
    import inspect

    accepted = set(inspect.signature(DeltaService.__init__).parameters)
    assert {field.name for field in dataclasses.fields(Services)} <= accepted
