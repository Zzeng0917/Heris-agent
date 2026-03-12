#include <iostream>
#include <vector>
#include <string>

using namespace std;

class Gomoku {
private:
    static const int SIZE = 15;
    vector<vector<char>> board;
    char currentPlayer;
    int moves;

public:
    Gomoku() : board(SIZE, vector<char>(SIZE, '.')), currentPlayer('X'), moves(0) {}

    void printBoard() {
        cout << "\n    ";
        for (int i = 0; i < SIZE; i++) {
            cout << (i < 10 ? " " : "") << i << " ";
        }
        cout << "\n   +";
        for (int i = 0; i < SIZE; i++) cout << "--";
        cout << "-\n";

        for (int i = 0; i < SIZE; i++) {
            cout << (i < 10 ? " " : "") << i << " |";
            for (int j = 0; j < SIZE; j++) {
                cout << board[i][j] << " ";
            }
            cout << "|\n";
        }

        cout << "   +";
        for (int i = 0; i < SIZE; i++) cout << "--";
        cout << "-\n";
    }

    bool isValidMove(int row, int col) {
        return row >= 0 && row < SIZE && col >= 0 && col < SIZE && board[row][col] == '.';
    }

    bool makeMove(int row, int col) {
        if (!isValidMove(row, col)) return false;
        board[row][col] = currentPlayer;
        moves++;
        return true;
    }

    bool checkWin(int row, int col) {
        char p = board[row][col];
        if (p == '.') return false;

        // 四个方向: 水平、垂直、两对角线
        int directions[4][2] = {{0, 1}, {1, 0}, {1, 1}, {1, -1}};

        for (auto& dir : directions) {
            int count = 1;
            int dr = dir[0], dc = dir[1];

            // 正向检查
            for (int i = 1; i < 5; i++) {
                int r = row + dr * i, c = col + dc * i;
                if (r < 0 || r >= SIZE || c < 0 || c >= SIZE || board[r][c] != p) break;
                count++;
            }

            // 反向检查
            for (int i = 1; i < 5; i++) {
                int r = row - dr * i, c = col - dc * i;
                if (r < 0 || r >= SIZE || c < 0 || c >= SIZE || board[r][c] != p) break;
                count++;
            }

            if (count >= 5) return true;
        }
        return false;
    }

    bool isDraw() {
        return moves == SIZE * SIZE;
    }

    void switchPlayer() {
        currentPlayer = (currentPlayer == 'X') ? 'O' : 'X';
    }

    char getCurrentPlayer() {
        return currentPlayer;
    }

    void play() {
        cout << "===== 五子棋游戏 =====\n";
        cout << "玩家 X  vs 玩家 O\n";
        cout << "输入格式: 行 列 (如: 7 7)\n\n";

        while (true) {
            printBoard();
            cout << "\n玩家 " << currentPlayer << " 的回合\n";
            cout << "请输入坐标 (行 列): ";

            int row, col;
            if (!(cin >> row >> col)) {
                cin.clear();
                cin.ignore(10000, '\n');
                cout << "输入无效，请重新输入!\n";
                continue;
            }

            if (!makeMove(row, col)) {
                cout << "无效的位置，请重新输入!\n";
                continue;
            }

            if (checkWin(row, col)) {
                printBoard();
                cout << "\n🎉 玩家 " << currentPlayer << " 获胜!\n";
                break;
            }

            if (isDraw()) {
                printBoard();
                cout << "\n平局!\n";
                break;
            }

            switchPlayer();
        }
    }
};

int main() {
    char playAgain;
    do {
        Gomoku game;
        game.play();
        cout << "\n是否再来一局? (y/n): ";
        cin >> playAgain;
    } while (playAgain == 'y' || playAgain == 'Y');

    cout << "感谢游玩!\n";
    return 0;
}
