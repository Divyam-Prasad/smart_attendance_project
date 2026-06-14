from PIL import Image
from pathlib import Path
import numpy as np
import cv2
import face_recognition
import datetime
import mysql.connector
import csv
import pickle
import time
from sleep_detector import SleepDetector          


def start_attendance_system(program, duration=45,headless = False):

    sleep_detector = SleepDetector()

    connection = mysql.connector.connect(
        host='localhost', user='root', password='root', database='STUDENTS'
    )
    cursor = connection.cursor()

    today = datetime.datetime.now().date()

    fileObj = open('student_info.csv', 'a+')
    writer = csv.writer(fileObj)
    writer.writerow(['Attendance for', program, today])
    writer.writerow(['Name', 'Time'])

    with open(r'C:\Users\Divyam\Desktop\Hackathon Project\Data\average-encodings.pickle', 'rb') as f:
        average_encoding_data = pickle.load(f)

    with open(r'C:\Users\Divyam\Desktop\Hackathon Project\Data\encodings.pickle', 'rb') as f:
        encoding_data = pickle.load(f)

    known_encodings  = []
    known_names_flat = []

    for name, encodings_list in encoding_data.items():
        for enc in encodings_list:
            known_encodings.append(enc)
            known_names_flat.append(name)

    for name, avg_enc in average_encoding_data.items():
        known_encodings.append(avg_enc)
        known_names_flat.append(name)

    assert len(known_encodings) == len(known_names_flat), "Encoding/name mismatch!"
    print(f"Loaded: {len(known_encodings)} encodings for {len(set(known_names_flat))} people")

    video_capture = cv2.VideoCapture(0)

    temp_face_name_list = []   # prevents duplicate attendance entries
    sleeping_logged     = set()  # ← prevents duplicate sleeping DB entries

    start_time   = time.time()
    current_time = start_time

    while current_time - start_time < duration * 60:
        ret, frame = video_capture.read()
        if not ret:
            print("Camera error")
            break

        resized_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
        rgb_frame = resized_frame[:, :, ::-1].astype('uint8')

        face_locations = face_recognition.face_locations(rgb_frame, model='hog')
        face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)

        if face_encodings:
            for face_enc, (top, right, bottom, left) in zip(face_encodings, face_locations):
                top *= 4; bottom *= 4; left *= 4; right *= 4

                face_distances   = face_recognition.face_distance(known_encodings, face_enc)
                best_match_index = np.argmin(face_distances)
                this_moment      = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                name             = 'Unknown Person'

                if face_distances[best_match_index] < 0.6:
                    name = known_names_flat[best_match_index]

                    is_sleeping, label, box_color = sleep_detector.check(
                        frame, name, (left, top, right, bottom)
                    )

                    # Log attendance once per session
                    if name not in temp_face_name_list:
                        temp_face_name_list.append(name)
                        writer.writerow([name, this_moment])
                        cursor.execute(
                            "INSERT INTO STUDENT_INFO (NAME, TIME, STATUS) VALUES(%s,%s,%s);",
                            (name, this_moment, 'SLEEPING' if is_sleeping else 'PRESENT')
                        )
                        connection.commit()

                    # Log sleeping once per sleep event, not every frame
                    if is_sleeping and name not in sleeping_logged:
                        sleeping_logged.add(name)
                        cursor.execute(
                            "INSERT INTO STUDENT_INFO (NAME, TIME, STATUS) VALUES(%s,%s,%s);",
                            (name, this_moment, 'SLEEPING')
                        )
                        connection.commit()
                    elif not is_sleeping:
                        sleeping_logged.discard(name)  # reset for next sleep event

                else:
                    label     = 'Unknown Person'
                    box_color = (255, 165, 0)

                    face_image  = cv2.cvtColor(frame[top:bottom, left:right], cv2.COLOR_BGR2RGB)
                    pil_image   = Image.fromarray(face_image)
                    safe_time   = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
                    destination = Path(r'C:\Users\Divyam\Desktop\Hackathon Project\Unknown Faces') / f'{safe_time}.jpg'
                    pil_image.save(destination)

                cv2.rectangle(frame, (left, top), (right, bottom), box_color, 2)
                cv2.putText(frame, label, (left + 6, bottom - 6),
                            cv2.FONT_HERSHEY_DUPLEX, 0.6, (255, 255, 255), 2)

        if headless:
            cv2.imshow('Attendance System', frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        current_time = time.time()

    video_capture.release()
    cv2.destroyAllWindows()
    fileObj.close()
    cursor.close()
    connection.close()

if __name__ == '__main__':
    start_attendance_system('Btech')