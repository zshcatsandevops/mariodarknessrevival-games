# off/pr/program.py

import pygame
import tkinter as tk
import random
import sys

# --- Constants ---
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
FPS = 60
TITLE = "GTA Pygame/Tkinter Edition"

# Colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
GRAY = (128, 128, 128) # Pavement color
BUILDING_COLOR = (50, 50, 50) # Dark gray for buildings
PEDESTRIAN_COLOR = (200, 150, 100) # A skin-like tone for pedestrians

# Player properties
PLAYER_SPEED = 5
PLAYER_SIZE = 30

# Pedestrian properties
PEDESTRIAN_SPEED = 2
PEDESTRIAN_SIZE = 25
NUM_PEDESTRIANS = 10

# --- Game Classes ---

class Player(pygame.sprite.Sprite):
    """ The player character """
    def __init__(self, game):
        super().__init__()
        self.game = game
        self.image = pygame.Surface((PLAYER_SIZE, PLAYER_SIZE))
        self.image.fill(BLUE)
        self.rect = self.image.get_rect()
        self.rect.center = (SCREEN_WIDTH / 2, SCREEN_HEIGHT / 2)
        self.vx, self.vy = 0, 0

    def update(self):
        """ Update player position based on key presses """
        self.vx, self.vy = 0, 0
        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            self.vx = -PLAYER_SPEED
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            self.vx = PLAYER_SPEED
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            self.vy = -PLAYER_SPEED
        if keys[pygame.K_DOWN] or keys[pygame.K_s]:
            self.vy = PLAYER_SPEED

        # Diagonal movement correction
        if self.vx != 0 and self.vy != 0:
            self.vx *= 0.7071
            self.vy *= 0.7071

        # Move and check for collisions
        self.rect.x += self.vx
        self.check_collision('x')
        self.rect.y += self.vy
        self.check_collision('y')

        # Keep player on screen
        if self.rect.right > SCREEN_WIDTH:
            self.rect.right = SCREEN_WIDTH
        if self.rect.left < 0:
            self.rect.left = 0
        if self.rect.bottom > SCREEN_HEIGHT:
            self.rect.bottom = SCREEN_HEIGHT
        if self.rect.top < 0:
            self.rect.top = 0

    def check_collision(self, direction):
        """ Check for collision with walls """
        hits = pygame.sprite.spritecollide(self, self.game.walls, False)
        if hits:
            if direction == 'x':
                if self.vx > 0: # Moving right
                    self.rect.right = hits[0].rect.left
                if self.vx < 0: # Moving left
                    self.rect.left = hits[0].rect.right
            if direction == 'y':
                if self.vy > 0: # Moving down
                    self.rect.bottom = hits[0].rect.top
                if self.vy < 0: # Moving up
                    self.rect.top = hits[0].rect.bottom

class Wall(pygame.sprite.Sprite):
    """ A static wall/building for collision """
    def __init__(self, x, y, width, height):
        super().__init__()
        self.image = pygame.Surface((width, height))
        self.image.fill(BUILDING_COLOR)
        self.rect = self.image.get_rect()
        self.rect.topleft = (x, y)

class Pedestrian(pygame.sprite.Sprite):
    """ A simple NPC that moves around """
    def __init__(self, game):
        super().__init__()
        self.game = game
        self.image = pygame.Surface((PEDESTRIAN_SIZE, PEDESTRIAN_SIZE))
        self.image.fill(PEDESTRIAN_COLOR)
        self.rect = self.image.get_rect()
        # Ensure they don't spawn inside a wall
        while True:
            self.rect.x = random.randrange(0, SCREEN_WIDTH - self.rect.width)
            self.rect.y = random.randrange(0, SCREEN_HEIGHT - self.rect.height)
            if not pygame.sprite.spritecollide(self, self.game.walls, False):
                break
        
        self.vx = random.choice([-PEDESTRIAN_SPEED, PEDESTRIAN_SPEED])
        self.vy = random.choice([-PEDESTRIAN_SPEED, PEDESTRIAN_SPEED])
        self.change_dir_timer = pygame.time.get_ticks()

    def update(self):
        """ Move the pedestrian and handle boundaries """
        self.rect.x += self.vx
        self.rect.y += self.vy

        # Change direction periodically
        now = pygame.time.get_ticks()
        if now - self.change_dir_timer > random.randrange(2000, 5000): # every 2-5 seconds
            self.change_dir_timer = now
            self.vx = random.choice([-PEDESTRIAN_SPEED, PEDESTRIAN_SPEED, 0])
            self.vy = random.choice([-PEDESTRIAN_SPEED, PEDESTRIAN_SPEED, 0])

        # Bounce off screen edges
        if self.rect.right > SCREEN_WIDTH or self.rect.left < 0:
            self.vx *= -1
        if self.rect.bottom > SCREEN_HEIGHT or self.rect.top < 0:
            self.vy *= -1
            
        # Bounce off walls
        hits = pygame.sprite.spritecollide(self, self.game.walls, False)
        if hits:
            # A simple bounce logic
            self.vx *= -1
            self.vy *= -1
            self.rect.x += self.vx * 2 # Move out of wall
            self.rect.y += self.vy * 2


class Game:
    """ Main game class """
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption(TITLE)
        self.clock = pygame.time.Clock()
        self.running = True

    def new(self):
        """ Start a new game """
        self.all_sprites = pygame.sprite.Group()
        self.walls = pygame.sprite.Group()
        self.pedestrians = pygame.sprite.Group()

        # Create player
        self.player = Player(self)
        self.all_sprites.add(self.player)

        # Create walls (buildings)
        wall_data = [
            (0, 0, 150, 100),
            (250, 150, 100, 200),
            (500, 50, 200, 80),
            (0, 400, 300, 100),
            (450, 350, 150, 150),
            (650, 500, 150, 100)
        ]
        for data in wall_data:
            wall = Wall(*data)
            self.all_sprites.add(wall)
            self.walls.add(wall)
        
        # Create pedestrians
        for _ in range(NUM_PEDESTRIANS):
            ped = Pedestrian(self)
            self.all_sprites.add(ped)
            self.pedestrians.add(ped)

        self.run()

    def run(self):
        """ Game Loop """
        self.playing = True
        while self.playing:
            self.clock.tick(FPS)
            self.events()
            self.update()
            self.draw()

    def events(self):
        """ Game Loop - Events """
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.playing = False
                self.running = False

    def update(self):
        """ Game Loop - Update """
        self.all_sprites.update()

    def draw(self):
        """ Game Loop - Draw """
        self.screen.fill(GRAY)
        self.all_sprites.draw(self.screen)
        pygame.display.flip()
        
    def quit(self):
        pygame.quit()
        sys.exit()

def start_game():
    """ Function to destroy Tkinter window and start Pygame """
    root.destroy()
    g = Game()
    while g.running:
        g.new()
    g.quit()

# --- Main Execution ---
if __name__ == '__main__':
    # Create the Tkinter menu window
    root = tk.Tk()
    root.title("Game Launcher")
    
    # Center the window
    window_width = 300
    window_height = 150
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    center_x = int(screen_width/2 - window_width / 2)
    center_y = int(screen_height/2 - window_height / 2)
    root.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')
    
    root.configure(bg='#333') # Dark background

    # Title Label
    title_label = tk.Label(
        root, 
        text="GTA Pygame", 
        font=("Arial", 24, "bold"),
        fg="white",
        bg='#333'
    )
    title_label.pack(pady=10)

    # Start Button
    start_button = tk.Button(
        root, 
        text="Start Game", 
        font=("Arial", 14),
        command=start_game,
        bg='#555',
        fg='white',
        activebackground='#777',
        activeforeground='white',
        padx=10,
        pady=5
    )
    start_button.pack(pady=10)

    # Run the Tkinter main loop
    root.mainloop()
