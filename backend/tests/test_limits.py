from app.models.tables import Asset
from app.services.limits import max_amount_base_units

SEPOLIA = 11_155_111
ONE_THOUSANDTH_ETH_WEI = 1_000_000_000_000_000
ONE_HUNDRED_DEMO_BASE_UNITS = 100_000_000_000_000_000_000


def test_max_amount_base_units_for_configured_assets() -> None:
    eth = Asset(chain_id=SEPOLIA, symbol="ETH", type="native", decimals=18)
    demo = Asset(chain_id=SEPOLIA, symbol="DEMO", type="erc20", decimals=18)
    nft = Asset(chain_id=SEPOLIA, symbol="KASA", type="erc721", decimals=0)

    assert max_amount_base_units(eth) == ONE_THOUSANDTH_ETH_WEI
    assert max_amount_base_units(demo) == ONE_HUNDRED_DEMO_BASE_UNITS
    assert max_amount_base_units(nft) is None
