//Fetch all recent team duel tokens:
await (async (userId) => {
  let token = "";
  let results = [];
  let page = 1;

  function extractIdsFromPayload(rawPayload) {
    let out = [];
    let parsed;

    try {
        parsed = JSON.parse(rawPayload);
    } catch {
        return out;
    }

    const items = Array.isArray(parsed) ? parsed : [parsed];

    for (const item of items) {
        // Check top level first
        let gameMode = item.gameMode;
        let gameId = item.gameId;

        // If not found, check payload
        if ((!gameMode || !gameId) && item.payload) {
            gameMode = item.payload.gameMode;
            gameId = item.payload.gameId;
        }

        if (gameMode === "TeamDuels" && gameId) {
            out.push(gameId);
        }
    }

    return out;
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
        results.push(...extractIdsFromPayload(entry.payload));
      }
    }

    if (!data.paginationToken) {
      console.log("No pagination token — stopping.");
      break;
    }

    token = data.paginationToken;

    await new Promise(r => setTimeout(r, 300)); // be nice to the server
  }

  results = [...new Set(results)];
  return results;
})("60314c8c098571000133cd25"); //change this to whatever your personal token is.



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

