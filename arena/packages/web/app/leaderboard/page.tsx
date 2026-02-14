import Link from "next/link";

export default function LeaderboardPage() {
  return (
    <main style={{ padding: 40, maxWidth: 900, margin: "0 auto" }}>
      <Link href="/" style={{ color: "#555", fontSize: 12, letterSpacing: 2 }}>
        &larr; ARENA
      </Link>
      <h1 style={{
        fontSize: 36,
        fontWeight: 900,
        color: "#39ff14",
        textShadow: "0 0 30px rgba(57,255,20,0.3)",
        marginTop: 8,
        marginBottom: 32,
      }}>
        LEADERBOARD
      </h1>
      <div style={{
        padding: 60,
        textAlign: "center",
        border: "1px dashed #222",
        color: "#444",
      }}>
        <p>No fights yet. Rankings will appear after the first battle.</p>
      </div>
    </main>
  );
}
