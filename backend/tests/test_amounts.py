import json
from pathlib import Path
from typing import TypedDict, cast

import pytest
from pydantic import BaseModel, ValidationError

from app.types.amount import BaseUnit, UnsignedBaseUnit, format_amount, parse_amount


class AssetFixture(BaseModel):
    symbol: str = "TST"
    decimals: int


class AmountModel(BaseModel):
    amount: BaseUnit


class UnsignedAmountModel(BaseModel):
    amount: UnsignedBaseUnit


class ParseFixture(TypedDict):
    decimals: int
    human: str
    base: str


class ParseErrorFixture(TypedDict):
    decimals: int
    human: str


class FormatFixture(TypedDict):
    decimals: int
    base: str
    human: str


class AmountFixtures(TypedDict):
    parse: list[ParseFixture]
    parseErrors: list[ParseErrorFixture]
    format: list[FormatFixture]


def _fixtures() -> AmountFixtures:
    path = Path(__file__).resolve().parents[2] / "packages" / "shared" / "fixtures" / "amounts.json"
    return cast(AmountFixtures, json.loads(path.read_text(encoding="utf-8")))


def test_parse_amount_vectors() -> None:
    fixtures = _fixtures()
    for row in fixtures["parse"]:
        asset = AssetFixture(decimals=row["decimals"])
        assert str(parse_amount(asset, row["human"])) == row["base"]


def test_parse_amount_error_vectors() -> None:
    fixtures = _fixtures()
    for row in fixtures["parseErrors"]:
        asset = AssetFixture(decimals=row["decimals"])
        with pytest.raises(ValueError):
            parse_amount(asset, row["human"])


def test_format_amount_vectors() -> None:
    fixtures = _fixtures()
    for row in fixtures["format"]:
        asset = AssetFixture(decimals=row["decimals"])
        assert format_amount(asset, row["base"]) == row["human"]


def test_base_unit_wire_validation_and_serialization() -> None:
    assert AmountModel(amount="123").amount == 123
    assert AmountModel(amount=-123).model_dump_json() == '{"amount":"-123"}'

    for bad in [True, 1.2, "01", "-01", "1.0", ""]:
        with pytest.raises(ValidationError):
            AmountModel(amount=bad)

    with pytest.raises(ValidationError):
        UnsignedAmountModel(amount="-1")
