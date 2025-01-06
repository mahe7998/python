import pygame
import random

# Initialize Pygame
pygame.init()

# Define some colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GRAY = (128, 128, 128)

# Set the width and height of each block
BLOCK_SIZE = 30

# Set the dimensions of the game board
BOARD_WIDTH = 10
BOARD_HEIGHT = 20

# Define the shapes
SHAPES = {
    'I': [[1, 1, 1, 1]],
    'J': [[1, 0, 0], [1, 1, 1]],
    'L': [[0, 0, 1], [1, 1, 1]],
    'O': [[1, 1], [1, 1]],
    'S': [[0, 1, 1], [1, 1, 0]],
    'T': [[0, 1, 0], [1, 1, 1]],
    'Z': [[1, 1, 0], [0, 1, 1]]
}

class Tetris:
    def __init__(self):
        self.screen = pygame.display.set_mode((BOARD_WIDTH * BLOCK_SIZE, BOARD_HEIGHT * BLOCK_SIZE))
        self.clock = pygame.time.Clock()
        self.board = [[0 for _ in range(BOARD_WIDTH)] for _ in range(BOARD_HEIGHT)]
        self.shape = None
        self.shape_x = 0
        self.shape_y = 0
        self.score = 0

    def new_shape(self):
        shape_name = random.choice(list(SHAPES.keys()))
        self.shape = SHAPES[shape_name]
        self.shape_x = BOARD_WIDTH // 2 - len(self.shape[0]) // 2
        self.shape_y = 0

    def rotate_shape(self):
        self.shape = [list(reversed(col)) for col in zip(*self.shape)]

    def move_shape_left(self):
        if self.shape_x > 0:
            self.shape_x -= 1

    def move_shape_right(self):
        if self.shape_x < BOARD_WIDTH - len(self.shape[0]):
            self.shape_x += 1

    def drop_shape(self):
        while True:
            collision = False
            for y, row in enumerate(self.shape):
                for x, val in enumerate(row):
                    if val == 1 and (self.shape_y + y >= BOARD_HEIGHT or self.board[self.shape_y + y][self.shape_x + x] == 1):
                        collision = True
                        break
                if collision:
                    break
            if collision:
                break
            self.shape_y += 1

    def check_collision(self):
        for y, row in enumerate(self.shape):
            for x, val in enumerate(row):
                if val == 1 and (self.shape_y + y >= BOARD_HEIGHT or self.board[self.shape_y + y][self.shape_x + x] == 1):
                    return True
        return False

    def update_board(self):
        for y, row in enumerate(self.shape):
            for x, val in enumerate(row):
                if val == 1:
                    self.board[self.shape_y + y][self.shape_x + x] = 1

    def check_lines(self):
        lines_to_remove = []
        for y, row in enumerate(self.board):
            if all(cell == 1 for cell in row):
                lines_to_remove.append(y)
        for line in sorted(lines_to_remove, reverse=True):
            del self.board[line]
            self.board.insert(0, [0 for _ in range(BOARD_WIDTH)])
            self.score += 100

    def draw_board(self):
        self.screen.fill(BLACK)
        for y, row in enumerate(self.board):
            for x, val in enumerate(row):
                if val == 1:
                    pygame.draw.rect(self.screen, WHITE, (x * BLOCK_SIZE, y * BLOCK_SIZE, BLOCK_SIZE, BLOCK_SIZE))
        for y, row in enumerate(self.shape):
            for x, val in enumerate(row):
                if val == 1:
                    pygame.draw.rect(self.screen, GRAY, ((self.shape_x + x) * BLOCK_SIZE, (self.shape_y + y) * BLOCK_SIZE, BLOCK_SIZE, 
BLOCK_SIZE))

    def run(self):
        self.new_shape()
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_LEFT:
                        self.move_shape_left()
                    elif event.key == pygame.K_RIGHT:
                        self.move_shape_right()
                    elif event.key == pygame.K_DOWN:
                        self.drop_shape()
                    elif event.key == pygame.K_UP:
                        self.rotate_shape()

            if self.check_collision():
                self.update_board()
                self.new_shape()
                self.check_lines()
            else:
                self.shape_y += 1

            self.draw_board()
            pygame.display.flip()
            self.clock.tick(60)

        pygame.quit()

if __name__ == "__main__":
    game = Tetris()
    game.run()
