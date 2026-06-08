import { expect } from "chai";
import { ethers } from "hardhat";

describe("DemoToken", () => {
  it("mints the initial supply to the owner with the right metadata", async () => {
    const [owner] = await ethers.getSigners();
    const token = await ethers.deployContract("DemoToken", [owner.address]);

    expect(await token.name()).to.equal("Demo Token");
    expect(await token.symbol()).to.equal("DEMO");
    expect(await token.decimals()).to.equal(18);
    expect(await token.balanceOf(owner.address)).to.equal(ethers.parseEther("1000000"));
  });

  it("transfers between accounts", async () => {
    const [owner, alice] = await ethers.getSigners();
    const token = await ethers.deployContract("DemoToken", [owner.address]);

    await token.transfer(alice.address, ethers.parseEther("100"));
    expect(await token.balanceOf(alice.address)).to.equal(ethers.parseEther("100"));
  });

  it("lets only the owner mint", async () => {
    const [owner, alice] = await ethers.getSigners();
    const token = await ethers.deployContract("DemoToken", [owner.address]);

    await token.mint(alice.address, ethers.parseEther("5"));
    expect(await token.balanceOf(alice.address)).to.equal(ethers.parseEther("5"));

    await expect(token.connect(alice).mint(alice.address, 1n)).to.be.revertedWithCustomError(
      token,
      "OwnableUnauthorizedAccount",
    );
  });
});
