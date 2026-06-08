// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {ERC721} from "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";

/// @title DemoCollectible — the ERC-721 admins mint to a user's deposit address in the demo.
/// @dev Sequential token ids; owner-only minting (the admin / ops role).
contract DemoCollectible is ERC721, Ownable {
    uint256 private _nextId;

    constructor(address initialOwner) ERC721("Kasa Collectible", "KASA") Ownable(initialOwner) {}

    /// @notice Mint the next collectible to `to`. Returns the minted token id.
    function mint(address to) external onlyOwner returns (uint256 tokenId) {
        tokenId = _nextId++;
        _safeMint(to, tokenId);
    }

    /// @notice Total number of tokens minted so far.
    function totalMinted() external view returns (uint256) {
        return _nextId;
    }
}
