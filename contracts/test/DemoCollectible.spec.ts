import { expect } from "chai";
import { ethers } from "hardhat";

describe("DemoCollectible", () => {
  it("has the right metadata", async () => {
    const [owner] = await ethers.getSigners();
    const nft = await ethers.deployContract("DemoCollectible", [owner.address]);
    expect(await nft.name()).to.equal("Kasa Collectible");
    expect(await nft.symbol()).to.equal("KASA");
  });

  it("admin mints sequential ids to a user", async () => {
    const [owner, user] = await ethers.getSigners();
    const nft = await ethers.deployContract("DemoCollectible", [owner.address]);

    await nft.mint(user.address);
    await nft.mint(user.address);

    expect(await nft.ownerOf(0)).to.equal(user.address);
    expect(await nft.ownerOf(1)).to.equal(user.address);
    expect(await nft.balanceOf(user.address)).to.equal(2n);
    expect(await nft.totalMinted()).to.equal(2n);
  });

  it("blocks non-owner minting", async () => {
    const [owner, user] = await ethers.getSigners();
    const nft = await ethers.deployContract("DemoCollectible", [owner.address]);

    await expect(nft.connect(user).mint(user.address)).to.be.revertedWithCustomError(
      nft,
      "OwnableUnauthorizedAccount",
    );
  });
});
