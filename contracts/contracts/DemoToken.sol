// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";

/// @title DemoToken — the ERC-20 Kasa indexes, credits, and withdraws on testnets.
/// @dev Owner-mintable so the demo faucet can fund user deposit addresses.
contract DemoToken is ERC20, Ownable {
    constructor(address initialOwner) ERC20("Demo Token", "DEMO") Ownable(initialOwner) {
        _mint(initialOwner, 1_000_000 ether);
    }

    /// @notice Mint new tokens. Restricted to the owner (the service hot wallet / faucet).
    function mint(address to, uint256 amount) external onlyOwner {
        _mint(to, amount);
    }
}
