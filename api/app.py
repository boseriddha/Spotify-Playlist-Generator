from flask import Flask, render_template, redirect, request
import openai, json, sys, requests, urllib.parse, base64, random, pprint
from dotenv import dotenv_values
from qrcodegen import *

config = dotenv_values(".env")

openai.api_key = config["OPENAI_API_KEY"]

app = Flask(
    __name__, template_folder="templates", static_url_path="", static_folder="static"
)

redirect_uri = "http://localhost:5000/authorized"
SCOPES = """user-read-private user-read-email playlist-read-private playlist-modify-private playlist-modify-public"""


def to_svg_str(qr: QrCode, border: int) -> str:
    if border < 0:
        raise ValueError("Border must be non-negative")
    parts: List[str] = []
    for y in range(qr.get_size()):
        for x in range(qr.get_size()):
            if qr.get_module(x, y):
                parts.append(f"M{x+border},{y+border}h1v1h-1z")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">
<svg xmlns="http://www.w3.org/2000/svg" version="1.1" viewBox="0 0 {qr.get_size()+border*2} {qr.get_size()+border*2}" stroke="none">
	<rect width="100%" height="100%" fill="#FFFFFF"/>
	<path d="{" ".join(parts)}" fill="#000000"/>
</svg>
"""


def get_playlist_description(prompt):
    messages = [
        {
            "role": "system",
            "content": "You are a helpful assistant which can generate a description for a spotify playlist based on the prompt given to you. You should analyse the prompt, understand it and give a one line description for a playlist which contains songs related to the prompt. Avoid using the same words which were provided in the prompt. Make sure that the description you generate, is humorous. Make sure you only return the description string without any keywords",
        },
        {"role": "user", "content": "songs for driving at night alone"},
        {
            "role": "assistant",
            "content": "The ultimate playlist for those nighttime contemplations behind the wheel - a symphony of solitude and starlit melodies.",
        },
        {"role": "user", "content": f"{prompt}"},
    ]

    response = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=messages)

    return response["choices"][0]["message"]["content"]


def get_playlist(prompt, count=10):
    example_json = """[
        {"song": "Hurt", "artist": "Johnny Cash"}, 
        {"song": "Nothing Compares 2 U", "artist": "Sinead O'Connor"}, 
        {"song": "Someone Like You", "artist": "Adele"}, 
        {"song": "Tears in Heaven", "artist": "Eric Clapton"}, 
        {"song": "Yesterday", "artist": "The Beatles"}, 
        {"song": "Losing My Religion", "artist": "R.E.M."}, 
        {"song": "Everybody Hurts", "artist": "R.E.M."}, 
        {"song": "My Immortal", "artist": "Evanescence"}, 
        {"song": "Fix You", "artist": "Coldplay"}, 
        {"song": "Nothing Else Matters", "artist": "Metallica"}
    ]"""

    messages = [
        {
            "role": "system",
            "content": """You are a helpful playlist generating assistant bot.
        You should generate a list of songs and artists according to a text prompt.
        You should return a JSON array which follows this format: {"song": <song_title>, "artist": <artist>}""",
        },
        {
            "role": "user",
            "content": "Generate a playlist of 10 songs based on this prompt: Sad songs",
        },
        {"role": "assistant", "content": example_json},
        {
            "role": "user",
            "content": f"Generate a playlist of {count} songs based on this prompt: {prompt}",
        },
    ]

    res = openai.ChatCompletion.create(
        model="gpt-3.5-turbo", messages=messages, max_tokens=400
    )

    playlist = json.loads(res["choices"][0]["message"]["content"])
    return playlist


def get_playlist_name(prompt):
    messages = [
        {
            "role": "system",
            "content": """You are a helpful bot which generates the name of a Spotify playlist 
        based on the prompt. The Spotify playlist contains songs which are related to the same prompt. Make sure the name
        you generate is only 2-3 words and a maximum of 4 english words. You should be humorous and funny while coming up
        with the name. You should only return the name string without adding any keywords.
        """,
        },
        {"role": "user", "content": "chill songs for monday evening"},
        {"role": "assistant", "content": "Unwind Grooves"},
        {"role": "user", "content": "office work"},
        {"role": "assistant", "content": "Melodic Mayhem"},
        {"role": "user", "content": f"{prompt}"},
    ]

    response = openai.ChatCompletion.create(messages=messages, model="gpt-3.5-turbo")

    return response["choices"][0]["message"]["content"]


def generate_string(length):
    text = ""
    possible = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    for i in range(length):
        text += possible[random.randint(0, len(possible) - 1)]
    return text


@app.get("/")
def index():
    return render_template("index.html")


# @app.post("/playlist")
# def request():
@app.post("/login")
def login():
    url = "https://accounts.spotify.com/authorize?"
    url += "client_id=" + config["SPOTIFY_CLIENT_ID"]
    url += "&response_type=code"
    url += "&redirect_uri=" + urllib.parse.quote(redirect_uri)
    url += "&state=" + generate_string(16)
    url += "&scope=" + SCOPES
    url += "&show_dialog=true"
    return redirect(url)


def fetch_access_token(code):
    SPOTIFY_ACCESS_URL = "https://accounts.spotify.com/api/token"
    body = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
    }

    concatenated_string = (
        config["SPOTIFY_CLIENT_ID"] + ":" + config["SPOTIFY_CLIENT_SECRET"]
    )
    encoded_bytes = base64.b64encode(concatenated_string.encode("utf-8"))
    encoded_string = encoded_bytes.decode("utf-8")

    headers = {
        "Authorization": f"Basic {encoded_string}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    r = requests.post(SPOTIFY_ACCESS_URL, data=body, headers=headers)

    content = r.json()

    return content


@app.get("/authorized")
def authorized():
    code = request.args.get("code")
    res = fetch_access_token(code)
    global ACCESS_TOKEN
    ACCESS_TOKEN = res["access_token"]
    global EXPIRES_IN
    EXPIRES_IN = res["expires_in"]
    global REFRESH_TOKEN
    REFRESH_TOKEN = res["refresh_token"]
    return render_template("search.html")


@app.post("/search")
def search():
    mood = request.form.get("mood")
    number = request.form.get("number")
    # name_playlist = request.form.get("namepl")
    playlist = get_playlist(mood, number)
    pl_description = get_playlist_description(mood)
    pl_name = get_playlist_name(mood)
    track_uris = []

    # getting the track ids
    for item in playlist:
        track, artist = item["song"], item["artist"]
        query = f"{track} {artist}"
        params = {"q": query, "type": "track"}
        content = requests.get(
            "https://api.spotify.com/v1/search",
            params=params,
            headers={"Authorization": f"Bearer {ACCESS_TOKEN}"},
        )
        search_results = content.json()
        track_uris.append(
            {
                "track": track,
                "artist": artist,
                "track_uri": search_results["tracks"]["items"][0]["uri"],
            }
        )

    # getting user info
    user = requests.get(
        "https://api.spotify.com/v1/me",
        headers={"Authorization": f"Bearer {ACCESS_TOKEN}"},
    )

    id = user.json()["id"]
    pprint.pprint(id)

    # creating a playlist
    url = f"https://api.spotify.com/v1/users/{id}/playlists"
    body = {
        "name": pl_name,
        "public": True,
        "collaborative": False,
        "description": pl_description,
    }
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    content = requests.post(url, json=body, headers=headers)

    # getting the playlist url
    playlist_url = content.json()["external_urls"]["spotify"]
    playlist_id = content.json()["id"]

    # adding tracks to the playlist
    uris = ",".join([item["track_uri"] for item in track_uris])
    url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks"
    url += "?position=0"
    url += "&uris=" + uris
    res = requests.post(url, headers={"Authorization": f"Bearer {ACCESS_TOKEN}"})

    # generating qr code
    qr0 = QrCode.encode_text(playlist_url, QrCode.Ecc.MEDIUM)
    svg = to_svg_str(qr0, 4)

    return render_template("results.html", qr_code=svg, link=playlist_url)
