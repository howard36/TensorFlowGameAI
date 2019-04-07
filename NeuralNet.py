local = True

if local:
    import keras
    from keras.layers import Input, Dense
    from keras.models import Model
    from keras.optimizers import Adam

    import numpy as np
    import math
    import random
    import copy
    import time

    from Node import Node
    from Game import *
else:
    auth.authenticate_user()
    gauth = GoogleAuth()
    gauth.credentials = GoogleCredentials.get_application_default()
    drive = GoogleDrive(gauth)

stateSize = 42
maxMoves = 7
batchsize = 32

def line():
    print('='*70)

class Net:
    def __init__(self, name, age, ID=''):
        self.name = name
        self.age = age
        self.filename = self.name + ', ' + str(self.age) + '.h5'
        if ID != '' and not local:
            f = drive.CreateFile({'id': ID})
            f.GetContentFile(self.filename)
            self.model = keras.models.load_model(self.filename)
        elif age != 0:
            self.model = keras.models.load_model(self.filename)
        else:
            inputs = Input(shape=(stateSize,))
            x = Dense(128, activation='relu')(inputs)
            x = Dense(128, activation='relu')(x)
            x = Dense(128, activation='relu')(x)
            x = Dense(128, activation='relu')(x)
            prob = Dense(maxMoves, activation='softmax')(x)
            value = Dense(1, activation='tanh')(x)

            self.model = Model(inputs=inputs, outputs=[prob, value])

            self.model.compile(optimizer=Adam(), loss=[
                               'categorical_crossentropy', 'mse'])

        self.model.summary()

    def simulate(self, start):
        cur = start
        while not cur.leaf:
            cur = cur.chooseBest()
            if cur == None:
                print("Error in simulate: cur is None")
                return
        if not cur.end:
            p, v = self.predictOne(cur.getState())
            if abs(sum(p)-1) > 0.0001:
                print("Error in simulate: Invalid probability distribution")
                print(p)
                return
            p.append(v)
            if any(math.isnan(i) for i in p):
                print("Error in simulate: NN output has nan")
                print(p)
                return
            cur.expand(p)
        else:
            v = cur.endVal
        while cur != start:
            v = -v
            cur.parent.update(v, cur)
            cur = cur.parent

    def selfPlay(self, sims):
        start = startStateC4()
        cur = Node(start)
        while not cur.end:
            for _ in range(sims):
                self.simulate(cur)
            cur = cur.chooseNewState()
        winner = cur.endVal
        cur = cur.parent
        allData = []
        # last = True
        while cur != None:
            prob = cur.getProbDistribution()
            winner = -winner
            data = [cur.getState(), prob, [winner]]
            # if last:
            #     print('Last state:')
            #     printBoardC4(data[0])
            #     print('MCTS: ')
            #     printOutputC4(prob, winner)
            #     print('NN: ')
            #     p, v = self.predictOne(data[0])
            #     printOutputC4(p, v)
            #     last = False
            #     line()
            allData += AddSymmetriesC4(data)
            cur = cur.parent
        return allData

    def learn(self, data):
        inputs = []
        probs = []
        values = []
        n = len(data)
        print("Data size = " + str(n))
        for i in range(n):
            inputs.append(data[i][0])
            probs.append(data[i][1])
            values.append(data[i][2])
        inputs = np.array(inputs).reshape(n, stateSize)
        probs = np.array(probs).reshape(n, maxMoves)
        values = np.array(values).reshape(n, 1)
        self.model.fit(inputs, [probs, values], epochs=1, batch_size=32)

    def train(self, games, sims):
        print("Start training")
        while True:
            allData = []
            start = time.time()
            for _ in range(games):
                allData += self.selfPlay(sims)
            end = time.time()
            print('Time to play %d games: %.2f seconds' % (games, end-start))
            self.learn(allData)
            self.age += 1
            print("Age = " + str(self.age))
            if self.age % 10 == 0:
                self.filename = self.name + ', ' + str(self.age) + '.h5'
                self.model.save(self.filename)
                if not local:
                    f = drive.CreateFile({'title': self.filename})
                    f.SetContentFile(self.filename)
                    f.Upload()
                    drive.CreateFile({'id': f.get('id')})
                print("Saved")

    def selectMove(self, state, sims, temp):
        print('Computer POV')
        if sims == 1:
            prob, value = self.predictOne(state)[0]
            print('NN: ', end='')
            printOutputC4(prob, value)
        else:
            cur = Node(state)
            for _ in range(sims):
                self.simulate(cur)
            prob = cur.getProbDistribution()
            value = max(cur.Q[i] for i in range(maxMoves) if cur.valid[i])
            print('MCTS: ', end='')
            printOutputC4(prob, value)
        valid = validMovesC4(state)
        prob = [prob[i] if valid[i] else 0 for i in range(maxMoves)]
        s = sum(prob)
        prob = [i/s for i in prob]
        if temp == 0:
            move = np.argmax(prob)
        else:
            move = np.random.choice(maxMoves, p=prob)
        p = prob[move]
        return (move, p)

    def playHuman(self, sims, temp=1):
        while True:
            first = input('Do you want to go first? (y/n) ')
            if first == 'y':
                turn = 1
            else:
                turn = -1
            state = startStateC4()
            lastCompState = startStateC4()
            history = []
            line()
            while True:
                if turn == 1:  # Human Turn
                    printBoardC4(state)
                    move = int(input('Your Move: '))
                    if 0 <= move < maxMoves and validMovesC4(state)[move]:
                        history.append(state.copy())
                        state = nextStateC4(state, move)
                    elif move == -1:
                        if len(history) == 0:
                            print('Cannot undo move! This is the starting state')
                        else:
                            state = history[-1].copy()
                            history.pop()
                            print('You undid your last move')
                        continue
                    elif move == -2:
                        line()
                        print('Predictions for current state (your turn)')
                        printBoardC4(state)
                        p, v = self.predictOne(state)
                        printOutputC4(p, v)
                        line()
                        continue
                    elif move == -3:
                        if state == [0]*9:
                            print(
                                'Cannot get predictions for previous state because it does not exist')
                            continue
                        line()
                        print('Predictions for previous state (computer turn)')
                        printBoardC4(lastCompState)
                        p, v = self.predictOne(lastCompState)
                        printOutputC4(p, v)
                        line()
                        continue
                    else:
                        print('Invalid Move! Choose a new move from this state:')
                        continue
                else:
                    lastCompState = state.copy()
                    move, prob = self.selectMove(state, sims, temp)
                    state = nextStateC4(state, move)
                    print("Computer's Move: " + str(move))
                    if prob < 0.1:
                        print('Unusual move played!')

                done, winner = evaluateStateC4(state)
                if done:
                    if winner == 1:
                        if turn == 1:
                            print('You won!')
                        else:
                            print('Computer won')
                    elif winner == -1:
                        print('Error: impossible to win on opponents turn')
                    else:
                        print('Tie')
                    printBoardC4([turn*i for i in state])
                    break
                state = [-i for i in state]
                turn = -turn
                line()
            if input('Play again? (Y/n) ') == 'n':
                break

    def predictOne(self, state):
        s = np.expand_dims(np.array(state), axis=0)
        p, v = self.model.predict(s)
        p = p[0].tolist()
        ss = sum(p)
        p = [i/ss for i in p]
        v = v[0][0]
        return (p, v)
