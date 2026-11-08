"""Agent STT uniquement pour les cours Mahay.

L'agent ne répond pas, ne diffuse pas de voix et ne conserve aucune trace
d'observabilité audio/vidéo. Il laisse AgentSession publier les transcriptions
texte sur le flux LiveKit lk.transcription.
"""
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, cli
from livekit.plugins import groq

server = AgentServer()


@server.rtc_session(agent_name="mahay-transcription")
async def transcrire_cours(ctx: JobContext) -> None:
    session = AgentSession(
        stt=groq.STT(
            model="whisper-large-v3-turbo",
            language="fr",
        ),
    )
    await session.start(
        agent=Agent(
            instructions=(
                "Tu es un moteur de transcription seulement. Tu n'engages aucune conversation, "
                "tu ne réponds pas aux participants et tu n'émets aucune voix. Transcris "
                "fidèlement la parole en français."
            )
        ),
        room=ctx.room,
        record=False,
    )
    await ctx.connect()


if __name__ == "__main__":
    cli.run_app(server)
