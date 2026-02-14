import { describe, it, expect, beforeEach } from "vitest";
import express from "express";
import request from "supertest";
import { createRouter } from "../../src/api/routes.js";
import { Lobby } from "../../src/state/lobby.js";

describe("Arena API", () => {
  let app: express.Express;
  let lobby: Lobby;

  beforeEach(() => {
    lobby = new Lobby();
    app = express();
    app.use(express.json());
    app.use("/api/v1", createRouter(lobby));
  });

  it("POST /arena/register creates agent", async () => {
    const res = await request(app).post("/api/v1/arena/register").send({
      agent_id: "bot_1",
      skills_md: "# Bot 1\nAggressive",
      wallet_address: "0x" + "a".repeat(40),
    });
    expect(res.status).toBe(200);
    expect(res.body.ok).toBe(true);
    expect(res.body.agent.id).toBe("bot_1");
  });

  it("POST /arena/register rejects duplicate", async () => {
    const body = { agent_id: "bot_1", skills_md: "# Bot", wallet_address: "0xaaa" };
    await request(app).post("/api/v1/arena/register").send(body);
    const res = await request(app).post("/api/v1/arena/register").send(body);
    expect(res.status).toBe(400);
  });

  it("GET /arena/agents lists registered agents", async () => {
    await request(app).post("/api/v1/arena/register").send({ agent_id: "a", skills_md: "#A", wallet_address: "0x1" });
    await request(app).post("/api/v1/arena/register").send({ agent_id: "b", skills_md: "#B", wallet_address: "0x2" });
    const res = await request(app).get("/api/v1/arena/agents");
    expect(res.body.agents).toHaveLength(2);
  });

  it("full fight flow: register → challenge → accept → fight → winner", async () => {
    await request(app).post("/api/v1/arena/register").send({ agent_id: "a", skills_md: "#A", wallet_address: "0x1" });
    await request(app).post("/api/v1/arena/register").send({ agent_id: "b", skills_md: "#B", wallet_address: "0x2" });

    const challenge = await request(app).post("/api/v1/arena/challenge").send({
      agent_id: "a", target_agent_id: "b", wager_amount: 10,
    });
    expect(challenge.body.ok).toBe(true);

    const accept = await request(app).post("/api/v1/arena/accept").send({
      agent_id: "b", challenge_id: challenge.body.challenge.id,
    });
    expect(accept.body.ok).toBe(true);
    const fightId = accept.body.fight_id;

    // Verify fight appears in active list
    const fights = await request(app).get("/api/v1/arena/fights");
    expect(fights.body.fights).toHaveLength(1);

    // Play until fight ends
    let state = accept.body.state;
    while (state.status !== "fight_over") {
      await request(app).post("/api/v1/arena/action").send({ agent_id: "a", fight_id: fightId, action: "heavy_punch" });
      const r = await request(app).post("/api/v1/arena/action").send({ agent_id: "b", fight_id: fightId, action: "taunt" });
      state = r.body.state;
      if (state.status === "round_over") {
        await request(app).post("/api/v1/arena/next-round").send({ fight_id: fightId });
        state = lobby.getFight(fightId)!.getState();
      }
    }
    expect(state.status).toBe("fight_over");
    expect(state.p1.roundWins).toBe(2);
  });
});
