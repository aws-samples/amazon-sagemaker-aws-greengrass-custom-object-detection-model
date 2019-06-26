import cv2
import argparse

# construct the argument parser and parse the arguments
ap = argparse.ArgumentParser()
ap.add_argument("-n", "--name-of-video", required=True, help="name of the video to record")

# 0 is typically your computer's built-in webcam.
# When we used a USB camera, we use 1 instead of 0
ap.add_argument("-c", "--camera-id", required=False, help="camera ID. 0 is typically your computer's built-in webcam.",
                default=0)


def main():
    args = vars(ap.parse_args())
    video_fname = args['name_of_video'] + ".mp4"
    camera_id = args['camera_id']

    cap = cv2.VideoCapture(camera_id)

    # Define the codec and create VideoWriter object. For mac mp4v or avi1 is the best option.
    # You can also use: 0x00000021 if this codec doesn't work for you
    fourcc = cv2.VideoWriter_fourcc('m', 'p', '4', 'v')

    # Create a video writer, specify the codec as well as the image widge and height.
    # cap.get(3) is the width, and cap.get(4) is the height of the camera in cap.
    out = cv2.VideoWriter(video_fname, fourcc, 5.0, (int(cap.get(3)), int(cap.get(4))))

    while (True):
        ret, frame = cap.read()

        if ret == True:
            out.write(frame)

            # Display the resulting frame
            cv2.imshow('frame', frame)

            # Keep recording until someone types `q` to stop the video
            if cv2.waitKey(1) & 0xFF == ord('q'):
                print("\nstop signal received.")
                break
        else:
            break

    # When everything done, release the capture
    cap.release()
    out.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
