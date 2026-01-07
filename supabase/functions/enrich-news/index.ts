import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "jsr:@supabase/supabase-js@2";

console.log("Asta News Enricher (Gemini 2.0 Flash): Online");

Deno.serve(async (req) => {
  try {
    const { record } = await req.json();

    // 1. Check API Key
    const apiKey = Deno.env.get("GEMINI_API_KEY");
    if (!apiKey) throw new Error("CRITICAL: GEMINI_API_KEY is missing.");
    
    // UPDATED: Using the model explicitly listed in your account
    const url = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${apiKey}`;

    const prompt = `
      You are a real estate analyst for the Ghanaian market. Analyze the following news snippet.
      Return a RAW JSON object (no markdown formatting) with these exact keys:
      {
        "sentiment_score": (number between -1.0 and 1.0),
        "ai_summary": (2 sentence executive summary),
        "relevance_score": (integer 1-10)
      }

      News Title: ${record.title}
      News Summary: ${record.summary}
    `;

    // 2. Call Gemini
    const aiResponse = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        contents: [{ parts: [{ text: prompt }] }],
        generationConfig: { response_mime_type: "application/json" }
      }),
    });

    const aiData = await aiResponse.json();

    // 3. Error Handling
    if (!aiData.candidates) {
      console.error("Gemini Raw Error:", JSON.stringify(aiData));
      return new Response(JSON.stringify({ 
        error: "Gemini API Rejected Request", 
        google_details: aiData 
      }), { status: 500, headers: { "Content-Type": "application/json" } });
    }

    // 4. Success Path
    const content = JSON.parse(aiData.candidates[0].content.parts[0].text);
    
    // Write to DB if it's a real record
    if (record.id && record.id !== "test-id-123") {
        const supabase = createClient(
          Deno.env.get("SUPABASE_URL") ?? "",
          Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? ""
        );
        await supabase.from("market_news").update({ ...content, status: "enriched" }).eq("id", record.id);
    }

    return new Response(JSON.stringify(content), {
      headers: { "Content-Type": "application/json" },
    });

  } catch (error) {
    return new Response(JSON.stringify({ error: error.message }), { status: 500, headers: { "Content-Type": "application/json" } });
  }
});
