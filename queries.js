// Fetch filtered duel tokens
async function fetchFilteredTokens(userId, { modeFilter = "all", gameType = "team" } = {}) {
    if (!["team", "duels"].includes(gameType)) {
        throw new Error('gameType must be either "team" or "duels"');
    }

    let token = "";
    let results = [];
    let page = 1;

    function extractIdsFromPayload(rawPayload) {
        const out = [];
        let parsed;

        try {
            parsed = JSON.parse(rawPayload);
        } catch (err) {
            console.warn("Failed to parse payload:", rawPayload, err);
            return out;
        }

        const items = Array.isArray(parsed) ? parsed : [parsed];

        for (const item of items) {
            const payload = item.payload || {};
            const gameMode = item.gameMode || payload.gameMode;
            const gameId = item.gameId || payload.gameId;
            const competitiveGameMode = payload.competitiveGameMode;
            const isCompetitive = competitiveGameMode && competitiveGameMode !== "None";

            if (!gameId || !gameMode) {
                continue;
            }

            // Game type filtering
            if (gameType === "team" && gameMode !== "TeamDuels") {
                continue;
            }
            if (gameType === "duels" && gameMode === "TeamDuels") {
                continue;
            }

            // Competitive/casual filtering
            if (modeFilter === "competitive" && !isCompetitive) {
                continue;
            }
            if (modeFilter === "casual" && isCompetitive) {
                continue;
            }
            out.push(gameId);
        }

        return out;
    }

    while (true) {
        let url = "https://www.geoguessr.com/api/v4/feed/private";
        if (token) url += "?paginationToken=" + token;

        console.log(`Fetching page ${page} with token:`, token || "none");
        const res = await fetch(url);
        const data = await res.json();

        if (!data.entries || data.entries.length === 0) {
            console.log("No more entries — stopping.");
            break;
        }

        for (const entry of data.entries) {
            if (typeof entry.payload === "string") {
                const ids = extractIdsFromPayload(entry.payload);
                results.push(...ids);
            } 
        }

        if (!data.paginationToken) {
            console.log("No pagination token — stopping.");
            break;
        }

        token = data.paginationToken;
        page++;
        await new Promise(r => setTimeout(r, 300)); 
    }

    const uniqueResults = [...new Set(results)];
    return uniqueResults;
}

// Usage example:
(async () => {
    const myUserId = "60314c8c098571000133cd25";
    let tokens = await fetchFilteredTokens(myUserId, { 
        modeFilter: "competitive", 
        gameType: "team" 
    });
    console.log("Final token list:", tokens);
})();




//Return most recent team duel summary link: 
await (async (userId) => {
  let token = "";
  let page = 1;

  function extractMostRecentTeamDuelId(rawPayload) {
    let parsed;
    try {
        parsed = JSON.parse(rawPayload);
    } catch {
        return null;
    }

    const items = Array.isArray(parsed) ? parsed : [parsed];

    for (const item of items) {
        // Top level first
        let gameMode = item.gameMode;
        let gameId = item.gameId;

        // If not found, check payload
        if ((!gameMode || !gameId) && item.payload) {
            gameMode = item.payload.gameMode;
            gameId = item.payload.gameId;
        }

        if (gameMode === "TeamDuels" && gameId) {
            return gameId; // return immediately on first match
        }
    }

    return null;
  }

  while (true) {
    let url = "https://www.geoguessr.com/api/v4/feed/private";
    if (token) url += "?paginationToken=" + token;

    console.log("Fetching page", page++);

    const res = await fetch(url);
    const data = await res.json();

    if (!data.entries || data.entries.length === 0) {
      console.log("No more entries — stopping.");
      break;
    }

    for (const entry of data.entries) {
      if (typeof entry.payload === "string") {
        const recentId = extractMostRecentTeamDuelId(entry.payload);
        if (recentId) {
          console.log(`https://www.geoguessr.com/team-duels/${recentId}/summary`);
          return recentId; // stop everything once we find it
        }
      }
    }

    if (!data.paginationToken) {
      console.log("No pagination token — stopping.");
      break;
    }

    token = data.paginationToken;
    await new Promise(r => setTimeout(r, 300));
  }

  console.log("No TeamDuels entries found.");
  return null;
})("60314c8c098571000133cd25"); //change for whoever needs to use it

//return stats for a given list of gameIDs
async function fetchTeamDuels(ids, myId, teammateId = null) {
    const results = [];

    for (let gameToken of ids) {
        console.log(`Fetching duel ${gameToken}...`);

        try {
            let res = await fetch(`https://game-server.geoguessr.com/api/duels/${gameToken}`);
            let game = await res.json();

            // Find MY team
            let myTeam = game.teams.find(t => t.players.some(p => p.playerId === myId));
            if (!myTeam) {
                console.log("Skipping: no team with myId", myId);
                continue;
            }

            // Filter by teammate if provided
            if (teammateId && !myTeam.players.some(p => p.playerId === teammateId)) {
                console.log(`Skipping: teammateId ${teammateId} not in team`);
                continue;
            }

            // --- Statistics structures ---
            let teamStats = {
                totalDistance: 0,
                totalScore: 0,
                totalRounds: 0,
                totalHealthChange: 0
            };

            let playerStats = {};
            let roundsMap = {};

            // Process player guesses
            for (let player of myTeam.players) {
                let pStats = { distance: 0, score: 0, rounds: [] };

                for (let guess of player.guesses) {
                    let round = game.rounds[guess.roundNumber - 1];
                    let roundTime = (new Date(guess.created) - new Date(round.startTime)) / 1000;

                    pStats.distance += guess.distance;
                    pStats.score += guess.score;

                    pStats.rounds.push({
                        roundNumber: guess.roundNumber,
                        distance: guess.distance,
                        score: guess.score,
                        time: roundTime,
                        country: round.panorama?.countryCode
                    });

                    if (!roundsMap[guess.roundNumber]) {
                        roundsMap[guess.roundNumber] = {
                            roundNumber: guess.roundNumber,
                            totalDistance: 0,
                            totalScore: 0,
                            totalHealthChange: 0,
                            countries: new Set()
                        };
                    }

                    roundsMap[guess.roundNumber].totalDistance += guess.distance;
                    roundsMap[guess.roundNumber].totalScore += guess.score;

                    if (round.panorama?.countryCode) {
                        roundsMap[guess.roundNumber].countries.add(round.panorama.countryCode);
                    }
                }

                teamStats.totalDistance += pStats.distance;
                teamStats.totalScore += pStats.score;
                teamStats.totalRounds += player.guesses.length;

                playerStats[player.playerId] = pStats;
            }

            // Process health changes
            for (let rr of myTeam.roundResults || []) {
                if (rr.healthBefore != null && rr.healthAfter != null) {
                    let delta = rr.healthAfter - rr.healthBefore;
                    teamStats.totalHealthChange += delta;

                    if (!roundsMap[rr.roundNumber]) {
                        roundsMap[rr.roundNumber] = {
                            roundNumber: rr.roundNumber,
                            totalDistance: 0,
                            totalScore: 0,
                            totalHealthChange: 0,
                            countries: new Set()
                        };
                    }

                    roundsMap[rr.roundNumber].totalHealthChange = delta;
                }
            }

            // Finalize round stats
            let roundStats = Object.values(roundsMap).map(r => ({
                roundNumber: r.roundNumber,
                totalDistance: r.totalDistance,
                totalScore: r.totalScore,
                totalHealthChange: r.totalHealthChange,
                countries: Array.from(r.countries)
            }));

            results.push({
                gameId: game.gameId,
                teamId: myTeam.id,
                teamStats,
                playerStats,
                roundStats
            });

            await new Promise(r => setTimeout(r, 100));
        } catch (err) {
            console.error("Error fetching/processing gameToken:", gameToken, err);
        }
    }

    // Save results to a downloadable file
    const blob = new Blob([JSON.stringify(results, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "team_duels_stats.json";
    a.click();
    URL.revokeObjectURL(url);

    console.log(`Saved ${results.length} games to team_duels_stats.json`);
}

// Usage example:
const ids = [];
const myId = "---> YOUR ID HERE <---";
const teammateId = "---> OPTIONAL TEAMMATE ID <---";
await fetchTeamDuels(ids, myId, teammateId);