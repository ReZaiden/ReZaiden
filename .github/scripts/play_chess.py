#!/usr/bin/env python3
"""
Interactive Chess (Community vs Community) script.
Handles move execution by visitors playing as both White and Black,
rendering the board to SVG, and updating the README.
"""

import os
import sys
import json
import argparse
import chess
import chess.svg

# Force UTF-8 output to prevent crashes on Windows console encoding limitations
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Constants
REPO_NAME = "ReZaiden/ReZaiden"
STATE_FILE = "output/chess.json"
SVG_FILE = "output/board.svg"
README_FILE = "README.md"
START_MARKER = "<!-- CHESS_START -->"
END_MARKER = "<!-- CHESS_END -->"

# Theme colors matching ReZaiden's profile theme
BOARD_COLORS = {
    "square light": "#21262d",
    "square dark": "#0d1117",
    "square light active": "#00FFAA22",
    "square dark active": "#00FFAA44",
    "margin": "#161b22",
    "coord": "#8b949e",
}


def load_game_state() -> dict:
    """Load the current game state from JSON or return a default starting state."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading state file: {e}. Starting new game.")
    
    # Default starting state
    return {
        "fen": chess.Board().fen(),
        "history": [],
        "last_move": None,
        "status": "playing",
        "contributors": {}
    }


def save_game_state(state: dict):
    """Save the current game state to JSON."""
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def render_board(board: chess.Board):
    """Render the board state to an SVG file with custom branding."""
    os.makedirs(os.path.dirname(SVG_FILE), exist_ok=True)
    
    lastmove = board.peek() if board.move_stack else None
    check_sq = board.king_of_board(board.turn) if board.is_check() else None
    
    # Generate SVG content
    svg_data = chess.svg.board(
        board,
        size=400,
        lastmove=lastmove,
        check=check_sq,
        colors=BOARD_COLORS
    )
    
    with open(SVG_FILE, "w", encoding="utf-8") as f:
        f.write(svg_data)
    print(f"Board rendered to {SVG_FILE}")


def group_legal_moves(board: chess.Board) -> dict:
    """Group legal moves by piece type to make them structured and legible."""
    grouped = {
        "Pawns": [],
        "Knights": [],
        "Bishops": [],
        "Rooks": [],
        "Queens": [],
        "Kings": []
    }
    
    piece_map = {
        chess.PAWN: "Pawns",
        chess.KNIGHT: "Knights",
        chess.BISHOP: "Bishops",
        chess.ROOK: "Rooks",
        chess.QUEEN: "Queens",
        chess.KING: "Kings"
    }
    
    for move in board.legal_moves:
        piece = board.piece_at(move.from_square)
        if piece:
            san = board.san(move)
            group_name = piece_map.get(piece.piece_type, "Pawns")
            grouped[group_name].append(san)
            
    # Sort lists alphabetically
    for k in grouped:
        grouped[k].sort()
        
    return grouped


def format_move_history(history: list) -> str:
    """Format full list of SAN moves into standard numbered turns."""
    formatted = []
    for i in range(0, len(history), 2):
        turn_num = i // 2 + 1
        white_move = history[i]
        black_move = history[i+1] if i+1 < len(history) else "..."
        formatted.append(f"{turn_num}. {white_move} {black_move}")
    
    # Return last 6 turns to keep the README clean
    recent = formatted[-6:]
    if len(formatted) > 6:
        return "... " + " | ".join(recent)
    return " | ".join(recent) if recent else "No moves played yet."


def update_readme(board: chess.Board, state: dict):
    """Inject the chess board, status, and move links into README.md."""
    if not os.path.exists(README_FILE):
        print(f"Error: {README_FILE} not found.")
        return
        
    with open(README_FILE, "r", encoding="utf-8") as f:
        content = f.read()
        
    # Build status lines
    if state["status"] == "playing":
        turn_label = "Community (White) ⚪" if board.turn == chess.WHITE else "Community (Black) ⚫"
        status_text = f"🟢 **Status:** Active Game | ♟️ **Turn:** {turn_label}"
    elif state["status"] == "checkmate":
        # The player who just moved won.
        # Since board.turn toggled after push, if it is now White's turn, Black won.
        winner = "Community (Black) ⚫" if board.turn == chess.WHITE else "Community (White) ⚪"
        status_text = f"🏆 **Status:** Game Over - Checkmate! Winner: **{winner}**"
    elif state["status"] in ("stalemate", "draw"):
        status_text = f"🤝 **Status:** Game Over - Draw ({state['status'].capitalize()})!"
    else:
        status_text = f"🏁 **Status:** Game Over ({state['status']})!"
        
    last_move_text = f"📝 **Last Move:** `{state['last_move']}`" if state["last_move"] else "📝 **Last Move:** None"
    
    # Build move links section
    moves_content = ""
    if state["status"] == "playing":
        side = "White ⚪" if board.turn == chess.WHITE else "Black ⚫"
        moves_content += f"#### 👥 Click a move to play for **{side}**:\n\n"
        grouped_moves = group_legal_moves(board)
        
        for piece_name, moves in grouped_moves.items():
            if moves:
                links = []
                for mv in moves:
                    escaped_mv = mv.replace("+", "%2B").replace("#", "%23")
                    link = f"[{mv}](https://github.com/{REPO_NAME}/issues/new?title=Chess%3A+Play+{escaped_mv}&body=Click+%22Submit+new+issue%22+to+execute+your+move.+Please+do+not+modify+the+title.)"
                    links.append(link)
                moves_content += f"* **{piece_name}:** {' | '.join(links)}\n"
    else:
        moves_content += "#### 🏁 The game has ended. Start a new one below!\n"
        
    # Restart link
    restart_link = f"### [🔄 Start a New Game](https://github.com/{REPO_NAME}/issues/new?title=Chess%3A+Start+New+Game&body=Click+%22Submit+new+issue%22+to+start+a+fresh+game.)"
    
    # Leaderboard / Top Players
    leaderboard = "No contributors yet."
    if state["contributors"]:
        sorted_users = sorted(state["contributors"].items(), key=lambda x: x[1], reverse=True)
        leaderboard_list = [f"@{usr} ({count})" for usr, count in sorted_users[:5]]
        leaderboard = ", ".join(leaderboard_list)
        
    history_text = format_move_history(state["history"])
    
    # Use a timestamp cache buster to force GitHub Camo to bypass caching
    import time
    cache_buster = int(time.time())
    
    # Compose the entire Chess Markdown block
    chess_block = f"""{START_MARKER}
### ♟️ Interactive Chess (Community vs Community)

<div align="center">
  <img src="https://raw.githubusercontent.com/{REPO_NAME}/main/{SVG_FILE}?v={cache_buster}" width="400" alt="Chess Board" />
  
  <br/>
  
  {status_text}  
  {last_move_text}
</div>

{moves_content}

---

📝 **Recent Moves:** {history_text}  
🏆 **Top Community Players:** {leaderboard}  

{restart_link}
{END_MARKER}"""

    # Replace block in README
    pattern = f"{START_MARKER}[\\s\\S]*?{END_MARKER}"
    import re
    if START_MARKER in content and END_MARKER in content:
        new_content = re.sub(pattern, chess_block, content)
    else:
        # Append to the end if markers aren't present
        new_content = content.rstrip() + "\n\n---\n\n" + chess_block + "\n"
        
    with open(README_FILE, "w", encoding="utf-8") as f:
        f.write(new_content)
    print("README.md updated with chess board and moves.")


def write_bot_msg(msg: str):
    """Write the execution output message to output/bot_msg.txt for the CI environment."""
    os.makedirs("output", exist_ok=True)
    with open("output/bot_msg.txt", "w", encoding="utf-8") as f:
        f.write(msg)
    print(f"Workflow Message: {msg}")


def main():
    parser = argparse.ArgumentParser(description="Play Interactive Chess in GitHub README.")
    parser.add_argument("--action", choices=["play", "new"], required=True, help="Action to perform")
    parser.add_argument("--move", help="SAN notation of the move to play (e.g. e4, Nf3)")
    parser.add_argument("--user", help="GitHub username of the player")
    
    args = parser.parse_args()
    
    state = load_game_state()
    board = chess.Board(state["fen"])
    
    if args.action == "new":
        print("Starting a new game...")
        board = chess.Board()
        new_state = {
            "fen": board.fen(),
            "history": [],
            "last_move": None,
            "status": "playing",
            "contributors": state.get("contributors", {})
        }
        save_game_state(new_state)
        render_board(board)
        update_readme(board, new_state)
        write_bot_msg("Started a new Chess game! Good luck! ♟️")
        return
        
    # Action is "play"
    if state["status"] != "playing":
        msg = f"Game is already over! Status: {state['status']}."
        write_bot_msg(msg)
        return
        
    if not args.move:
        msg = "Error: --move is required when action is 'play'."
        write_bot_msg(msg)
        return
        
    user_move_str = args.move.strip()
    
    # 1. Parse and apply the move
    try:
        move = board.parse_san(user_move_str)
    except ValueError:
        msg = f"⚠️ Error: **{user_move_str}** is not a valid chess move (SAN notation)."
        write_bot_msg(msg)
        return
        
    if move not in board.legal_moves:
        msg = f"⚠️ Error: **{user_move_str}** is an illegal move in the current position."
        write_bot_msg(msg)
        return
        
    # Execute the move
    side_moved = "White" if board.turn == chess.WHITE else "Black"
    board.push(move)
    state["history"].append(user_move_str)
    
    # Update contributor stats
    player_username = args.user.strip() if args.user else "Anonymous"
    state["contributors"][player_username] = state["contributors"].get(player_username, 0) + 1
    
    state["last_move"] = f"{user_move_str} (by @{player_username})"
        
    # Check game status
    if board.is_game_over():
        if board.is_checkmate():
            state["status"] = "checkmate"
            msg = f"🏆 **Checkmate!** @{player_username} played **{user_move_str}** ({side_moved}) and won the game! 🎉"
        elif board.is_stalemate():
            state["status"] = "stalemate"
            msg = f"🤝 **Stalemate!** @{player_username} played **{user_move_str}** ({side_moved}), resulting in a draw."
        else:
            state["status"] = "draw"
            msg = f"🤝 **Draw!** @{player_username} played **{user_move_str}** ({side_moved}), ending the game."
    else:
        next_side = "Black ⚫" if board.turn == chess.BLACK else "White ⚪"
        msg = f"👥 @{player_username} played **{user_move_str}** ({side_moved})! It is now turn for **{next_side}**."
            
    state["fen"] = board.fen()
    save_game_state(state)
    render_board(board)
    update_readme(board, state)
    write_bot_msg(msg)


if __name__ == "__main__":
    main()
